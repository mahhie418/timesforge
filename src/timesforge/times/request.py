"""Requests for times channels, reserved so that no two of them create the same channel."""

import dataclasses
import datetime
import sqlite3
import typing

import timesforge.storage
import timesforge.times.naming
import timesforge.times.policy

type Status = typing.Literal['reserved', 'pending_name_resolution']

_OPEN_SELECT = "SELECT request_id, user_id, first_name, channel_name, request_status, grant_id, create_time FROM request WHERE workspace_id = ? AND user_id = ? AND request_status IN ('reserved', 'pending_name_resolution')"
_NAME_SELECT = "SELECT 1 FROM channel WHERE workspace_id = ? AND channel_name = ? AND channel_status != 'deleted' UNION ALL SELECT 1 FROM request WHERE workspace_id = ? AND channel_name = ? AND request_status = 'reserved'"
_GRANT_RESERVE = "UPDATE recreation SET grant_status = 'reserved', reserve_time = ? WHERE workspace_id = ? AND user_id = ? AND grant_status = 'unused' RETURNING grant_id"
_REQUEST_INSERT = 'INSERT INTO request (workspace_id, user_id, first_name, channel_name, request_status, grant_id, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING request_id, user_id, first_name, channel_name, request_status, grant_id, create_time'

class RequestRefusedError(Exception):

    """Raised when a member may not create a times channel.

    Attributes:
        refusal: Why not, as `timesforge.times.policy.decide` tells.
    """

    def __init__(
        self,
        refusal: timesforge.times.policy.Refusal
    ) -> None:

        """Initialises the error.

        Args:
            refusal: Why the member may not create a times channel.
        """

        super().__init__(f'The member may not create a times channel: {refusal}')

        self.refusal = refusal

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Request:

    """One request for a times channel.

    Attributes:
        request_id: ID of the request.
        user_id: Slack user ID of the member who asked, who is to hold the channel.
        first_name: First name that the member entered.
        channel_name: Name of the channel, made from the first name.
        status: reserved while the channel waits to be created, or pending_name_resolution while another channel has its name.
        grant_id: ID of the recreation grant reserved for the channel, or None when the member uses their first right.
        creation: When the member asked.
    """

    request_id: int
    user_id: str
    first_name: str
    channel_name: str
    status: Status
    grant_id: int | None
    creation: datetime.datetime

class RequestIO:

    """Reads and writes the requests for times channels of each workspace."""

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the requests.
        """

        self._database = database

    def reserve(
        self,
        workspace_id: str,
        user_id: str,
        first_name: str,
        now: datetime.datetime
    ) -> Request:

        """Reserves a times channel for a member.

        The checks and the reservation happen in one transaction, so that
        requests at the same moment, such as a button pressed twice or a
        request that Slack sends again, never reserve two channels. While a
        member has a request open, asking again returns that request. When
        the member needs a recreation grant, the request reserves it.

        A name that a times channel which is not deleted or another reserved
        request has already leaves the request pending, rather than reserved.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            first_name: First name that the member entered.
            now: The current time.

        Returns:
            The open request of the member.

        Raises:
            timesforge.times.naming.NameInvalidError: The first name cannot make
                                                      the name of a times channel.
            RequestRefusedError: The member may not create a times channel.
        """

        channel_name = timesforge.times.naming.sanitise(first_name)

        with self._database.begin() as connection:

            if (row := connection.execute(_OPEN_SELECT, (workspace_id, user_id)).fetchone()) is not None: return _decode(row)
            if (refusal := timesforge.times.policy.decide(connection, workspace_id, user_id)) is not None: raise RequestRefusedError(refusal)

            grant = connection.execute(_GRANT_RESERVE, (now.isoformat(), workspace_id, user_id)).fetchone()
            taken = connection.execute(_NAME_SELECT, (workspace_id, channel_name, workspace_id, channel_name)).fetchone() is not None
            values = (workspace_id, user_id, first_name.strip(), channel_name, 'pending_name_resolution' if taken else 'reserved', None if grant is None else grant['grant_id'], now.isoformat(), now.isoformat())

            return _decode(connection.execute(_REQUEST_INSERT, values).fetchone())

def _decode(
    row: sqlite3.Row
) -> Request:

    return Request(request_id = row['request_id'], user_id = row['user_id'], first_name = row['first_name'], channel_name = row['channel_name'], status = row['request_status'], grant_id = row['grant_id'], creation = datetime.datetime.fromisoformat(row['create_time']))
