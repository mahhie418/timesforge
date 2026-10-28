"""Requests for times channels, reserved so that no two of them create the same channel."""

import dataclasses
import datetime
import sqlite3
import typing

import timesforge.storage
import timesforge.times.history
import timesforge.times.naming
import timesforge.times.policy
import timesforge.times.registry

type Status = typing.Literal['reserved', 'pending_name_resolution', 'creating', 'reconciling', 'created', 'inviting', 'completed', 'failed']

_REQUEST_SELECT = 'SELECT request_id, user_id, first_name, channel_name, request_status, grant_id, channel_id, error_message, create_time FROM request WHERE workspace_id = ? AND request_id = ?'
_USER_SELECT = 'SELECT request_id, user_id, first_name, channel_name, request_status, grant_id, channel_id, error_message, create_time FROM request WHERE workspace_id = ? AND user_id = ? ORDER BY request_id'
_OPEN_SELECT = "SELECT request_id, user_id, first_name, channel_name, request_status, grant_id, channel_id, error_message, create_time FROM request WHERE workspace_id = ? AND user_id = ? AND request_status IN ('reserved', 'pending_name_resolution', 'creating', 'reconciling')"
_NAME_SELECT = "SELECT 1 FROM channel WHERE workspace_id = ? AND channel_name = ? AND channel_status != 'deleted' UNION ALL SELECT 1 FROM request WHERE workspace_id = ? AND channel_name = ? AND request_status IN ('reserved', 'creating', 'reconciling')"
_GRANT_RESERVE = "UPDATE recreation SET grant_status = 'reserved', reserve_time = ? WHERE workspace_id = ? AND user_id = ? AND grant_status = 'unused' RETURNING grant_id"
_REQUEST_INSERT = 'INSERT INTO request (workspace_id, user_id, first_name, channel_name, request_status, grant_id, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING request_id, user_id, first_name, channel_name, request_status, grant_id, channel_id, error_message, create_time'
_REQUEST_START = "UPDATE request SET request_status = 'creating', update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'reserved'"
_REQUEST_RETRY = "UPDATE request SET request_status = 'creating', update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'reconciling'"
_REQUEST_LOSE = "UPDATE request SET request_status = 'reconciling', error_message = ?, update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'creating'"
_REQUEST_POSTPONE = "UPDATE request SET request_status = 'pending_name_resolution', update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'creating'"
_REQUEST_FAIL = "UPDATE request SET request_status = 'failed', error_message = ?, update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status IN ('creating', 'reconciling') RETURNING grant_id"
_REQUEST_FINISH = "UPDATE request SET request_status = 'created', channel_id = ?, error_message = NULL, update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status IN ('creating', 'reconciling') RETURNING user_id, grant_id"
_REQUEST_ADVANCE = "UPDATE request SET request_status = 'inviting', update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'created'"
_REQUEST_COMPLETE = "UPDATE request SET request_status = 'completed', update_time = ? WHERE workspace_id = ? AND request_id = ? AND request_status = 'inviting'"
_GRANT_RELEASE = "UPDATE recreation SET grant_status = 'unused', reserve_time = NULL WHERE grant_id = ? AND grant_status = 'reserved'"
_GRANT_CONSUME = "UPDATE recreation SET grant_status = 'consumed', consume_time = ?, channel_id = ? WHERE grant_id = ? AND grant_status = 'reserved'"

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
        status: reserved while the channel waits to be created, pending_name_resolution while another channel has its name, creating while Slack creates it, reconciling while nobody knows whether Slack created it, created once it exists, inviting while members are invited to it, completed once they are, or failed when Slack refused to create it.
        grant_id: ID of the recreation grant reserved for the channel, or None when the member uses their first right.
        channel_id: Slack channel ID of the channel, or None until it is created.
        error: Why the last attempt failed or was lost, or None.
        creation: When the member asked.
    """

    request_id: int
    user_id: str
    first_name: str
    channel_name: str
    status: Status
    grant_id: int | None
    channel_id: str | None = None
    error: str | None = None
    creation: datetime.datetime

class RequestIO:

    """Reads and writes the requests for times channels of each workspace.

    A request moves on only from the statuses that lead to the next one, so
    that two callers at once never both create its channel.
    """

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the requests.
        """

        self._database = database

    def load(
        self,
        workspace_id: str,
        request_id: int
    ) -> Request | None:

        """Loads a request.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.

        Returns:
            The request, or None when it does not exist.
        """

        row = self._database.connect().execute(_REQUEST_SELECT, (workspace_id, request_id)).fetchone()

        return None if row is None else _decode(row)

    def find(
        self,
        workspace_id: str,
        user_id: str
    ) -> list[Request]:

        """Finds the requests of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.

        Returns:
            The requests, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_USER_SELECT, (workspace_id, user_id))]

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

        A name that a times channel which is not deleted or another open
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

    def start(
        self,
        workspace_id: str,
        request_id: int,
        now: datetime.datetime
    ) -> bool:

        """Marks a reserved request as being created.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            now: The current time.

        Returns:
            Whether the caller may create the channel now; False when the
            request is not reserved, such as when another caller creates it.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_START, (now.isoformat(), workspace_id, request_id)).rowcount == 1

    def retry(
        self,
        workspace_id: str,
        request_id: int,
        now: datetime.datetime
    ) -> bool:

        """Marks a request whose result was unknown as being created again.

        The caller must have made sure that Slack did not create the channel.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            now: The current time.

        Returns:
            Whether the caller may create the channel now; False when the
            result of the request is not unknown, such as when another caller
            settled it.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_RETRY, (now.isoformat(), workspace_id, request_id)).rowcount == 1

    def lose(
        self,
        workspace_id: str,
        request_id: int,
        *,
        error: str,
        now: datetime.datetime
    ) -> bool:

        """Records that nobody knows whether Slack created the channel of a request.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            error: What went wrong, such as a timeout.
            now: The current time.

        Returns:
            Whether the request was being created.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_LOSE, (error, now.isoformat(), workspace_id, request_id)).rowcount == 1

    def postpone(
        self,
        workspace_id: str,
        request_id: int,
        now: datetime.datetime
    ) -> bool:

        """Leaves a request pending, because a channel in Slack has its name.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            now: The current time.

        Returns:
            Whether the request was being created.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_POSTPONE, (now.isoformat(), workspace_id, request_id)).rowcount == 1

    def fail(
        self,
        workspace_id: str,
        request_id: int,
        *,
        error: str,
        now: datetime.datetime
    ) -> bool:

        """Records that Slack refused to create the channel of a request.

        The recreation grant of the request, if it has one, becomes unused
        again, because no channel took it.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            error: Why Slack refused.
            now: The current time.

        Returns:
            Whether the request was being created, or its result was unknown.
        """

        with self._database.begin() as connection:

            if (row := connection.execute(_REQUEST_FAIL, (error, now.isoformat(), workspace_id, request_id)).fetchone()) is None: return False

            connection.execute(_GRANT_RELEASE, (row['grant_id'],))

            return True

    def finish(
        self,
        workspace_id: str,
        request_id: int,
        channel: timesforge.times.registry.Channel,
        *,
        creator_id: str,
        now: datetime.datetime
    ) -> bool:

        """Registers the channel that Slack created for a request.

        The request, the registry, the recreation grant and the history change
        in one transaction, so that the channel is never registered without
        the request being done, or the other way round.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            channel: The channel, held by the member who asked.
            creator_id: Slack user ID of the user that Slack records as the creator of the channel.
            now: The current time.

        Returns:
            Whether the request was being created, or its result was unknown.

        Raises:
            timesforge.times.registry.ChannelDuplicateError: The channel or its
                                                             holder is registered already.
        """

        with self._database.begin() as connection:

            if (row := connection.execute(_REQUEST_FINISH, (channel.channel_id, now.isoformat(), workspace_id, request_id)).fetchone()) is None: return False

            timesforge.times.registry.insert(connection, workspace_id, channel)
            connection.execute(_GRANT_CONSUME, (now.isoformat(), channel.channel_id, row['grant_id']))
            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'create', actor_id = row['user_id'], target_id = row['user_id'], channel_id = channel.channel_id, details = {'creator': creator_id}, creation = now))

            return True

    def advance(
        self,
        workspace_id: str,
        request_id: int,
        now: datetime.datetime
    ) -> bool:

        """Marks a request whose channel was created as inviting members to it.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            now: The current time.

        Returns:
            Whether the caller may invite the members now.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_ADVANCE, (now.isoformat(), workspace_id, request_id)).rowcount == 1

    def complete(
        self,
        workspace_id: str,
        request_id: int,
        now: datetime.datetime
    ) -> bool:

        """Marks a request whose members were invited as completed.

        Members whom Slack refused do not keep the request open; inviting
        them again does not need it.

        Args:
            workspace_id: Slack workspace ID.
            request_id: ID of the request.
            now: The current time.

        Returns:
            Whether the request was inviting members.
        """

        with self._database.begin() as connection: return connection.execute(_REQUEST_COMPLETE, (now.isoformat(), workspace_id, request_id)).rowcount == 1

def _decode(
    row: sqlite3.Row
) -> Request:

    return Request(request_id = row['request_id'], user_id = row['user_id'], first_name = row['first_name'], channel_name = row['channel_name'], status = row['request_status'], grant_id = row['grant_id'], channel_id = row['channel_id'], error = row['error_message'], creation = datetime.datetime.fromisoformat(row['create_time']))
