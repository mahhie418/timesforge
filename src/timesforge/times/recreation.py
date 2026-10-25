"""Recreation grants, which the owner gives members whose times channels were deleted."""

import dataclasses
import datetime
import sqlite3
import typing

import timesforge.storage
import timesforge.times.history
import timesforge.times.policy

type Status = typing.Literal['unused', 'reserved', 'consumed', 'revoked']
type Reason = typing.Literal['excluded', 'holder', 'grant', 'right']

_GRANT_SELECT = 'SELECT grant_id, user_id, grant_status, grant_user, grant_time, revoke_time, reserve_time, consume_time, channel_id FROM recreation WHERE workspace_id = ? AND user_id = ? ORDER BY grant_id'
_OPEN_SELECT = "SELECT 1 FROM recreation WHERE workspace_id = ? AND user_id = ? AND grant_status IN ('unused', 'reserved')"
_GRANT_INSERT = "INSERT INTO recreation (workspace_id, user_id, grant_status, grant_user, grant_time) VALUES (?, ?, 'unused', ?, ?) RETURNING grant_id, user_id, grant_status, grant_user, grant_time, revoke_time, reserve_time, consume_time, channel_id"
_GRANT_REVOKE = "UPDATE recreation SET grant_status = 'revoked', revoke_time = ? WHERE workspace_id = ? AND user_id = ? AND grant_status = 'unused'"
_GRANT_CONSUME = "UPDATE recreation SET grant_status = 'consumed', consume_time = ?, channel_id = ? WHERE workspace_id = ? AND user_id = ? AND grant_status IN ('unused', 'reserved')"

class GrantInvalidError(ValueError):

    """Raised when the owner cannot give a member a recreation grant.

    Attributes:
        reason: Why not: excluded when the owner excluded the member, holder when they hold a times channel that is not deleted, grant when they have a grant that is not used up yet, or right when they have not used their first right yet.
    """

    def __init__(
        self,
        reason: Reason,
        message: str
    ) -> None:

        """Initialises the error.

        Args:
            reason: Why the member cannot get a recreation grant.
            message: Explanation for the owner.
        """

        super().__init__(message)

        self.reason = reason

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Grant:

    """One recreation grant.

    Attributes:
        grant_id: ID of the grant.
        user_id: Slack user ID of the member.
        status: Whether the grant is unused, reserved by a request for a times channel, consumed by the new channel, or revoked by the owner.
        owner_id: Slack user ID of the owner who gave the grant.
        granting: When the owner gave the grant.
        revocation: When the owner revoked the grant, or None while it is not revoked.
        reservation: When a request reserved the grant, or None while it is not reserved.
        consumption: When the member used the grant, or None while it is not used.
        channel_id: Slack channel ID of the times channel created with the grant, or None while it is not used.
    """

    grant_id: int
    user_id: str
    status: Status
    owner_id: str
    granting: datetime.datetime
    revocation: datetime.datetime | None = None
    reservation: datetime.datetime | None = None
    consumption: datetime.datetime | None = None
    channel_id: str | None = None

class RecreationIO:

    """Reads and writes the recreation grants of each workspace.

    A grant lets a member whose times channel was deleted create one more.
    Each member has at most one grant that is unused or reserved. Giving and
    revoking grants go into the history.
    """

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the grants.
        """

        self._database = database

    def find(
        self,
        workspace_id: str,
        user_id: str
    ) -> list[Grant]:

        """Finds the recreation grants of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.

        Returns:
            The grants, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_GRANT_SELECT, (workspace_id, user_id))]

    def grant(
        self,
        workspace_id: str,
        user_id: str,
        *,
        owner_id: str,
        now: datetime.datetime
    ) -> Grant:

        """Gives a member a recreation grant.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            owner_id: Slack user ID of the owner.
            now: The current time.

        Returns:
            The new grant.

        Raises:
            GrantInvalidError: The member may create a times channel already,
                               or may not get a grant.
        """

        with self._database.begin() as connection:

            match timesforge.times.policy.decide(connection, workspace_id, user_id):

                case 'excluded': raise GrantInvalidError('excluded', f'{user_id} is excluded from creating times channels')
                case 'holder': raise GrantInvalidError('holder', f'{user_id} holds a times channel that is not deleted')
                case _ if connection.execute(_OPEN_SELECT, (workspace_id, user_id)).fetchone() is not None: raise GrantInvalidError('grant', f'{user_id} has a recreation grant that is not used up')
                case None: raise GrantInvalidError('right', f'{user_id} has not created a times channel yet')
                case 'used':

                    grant = _decode(connection.execute(_GRANT_INSERT, (workspace_id, user_id, owner_id, now.isoformat())).fetchone())
                    timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'grant', actor_id = owner_id, target_id = user_id, details = {'grant_id': str(grant.grant_id)}, creation = now))

                    return grant

    def revoke(
        self,
        workspace_id: str,
        user_id: str,
        *,
        owner_id: str,
        now: datetime.datetime
    ) -> bool:

        """Revokes the unused recreation grant of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            owner_id: Slack user ID of the owner.
            now: The current time.

        Returns:
            Whether the member had an unused grant.
        """

        with self._database.begin() as connection:

            if connection.execute(_GRANT_REVOKE, (now.isoformat(), workspace_id, user_id)).rowcount != 1: return False

            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'revoke', actor_id = owner_id, target_id = user_id, creation = now))

            return True

    def consume(
        self,
        workspace_id: str,
        user_id: str,
        channel_id: str,
        now: datetime.datetime
    ) -> bool:

        """Uses the unused or reserved recreation grant of a member for a new times channel.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            channel_id: Slack channel ID of the new times channel.
            now: When the channel was created.

        Returns:
            Whether the member had an unused or reserved grant.
        """

        with self._database.begin() as connection: return connection.execute(_GRANT_CONSUME, (now.isoformat(), channel_id, workspace_id, user_id)).rowcount == 1

def _decode(
    row: sqlite3.Row
) -> Grant:

    revocation, reservation, consumption = (None if row[name] is None else datetime.datetime.fromisoformat(row[name]) for name in ('revoke_time', 'reserve_time', 'consume_time'))

    return Grant(grant_id = row['grant_id'], user_id = row['user_id'], status = row['grant_status'], owner_id = row['grant_user'], granting = datetime.datetime.fromisoformat(row['grant_time']), revocation = revocation, reservation = reservation, consumption = consumption, channel_id = row['channel_id'])
