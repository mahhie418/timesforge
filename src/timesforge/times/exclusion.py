"""Members whom the owner excluded from creating times channels."""

import dataclasses
import datetime
import sqlite3

import timesforge.storage
import timesforge.times.history

_EXCLUSION_SELECT = 'SELECT user_id, exclusion_reason, create_user, create_time FROM exclusion WHERE workspace_id = ? AND user_id = ?'
_WORKSPACE_SELECT = 'SELECT user_id, exclusion_reason, create_user, create_time FROM exclusion WHERE workspace_id = ? ORDER BY create_time'
_EXCLUSION_INSERT = 'INSERT INTO exclusion (workspace_id, user_id, exclusion_reason, create_user, create_time) VALUES (?, ?, ?, ?, ?) ON CONFLICT (workspace_id, user_id) DO NOTHING'
_EXCLUSION_DELETE = 'DELETE FROM exclusion WHERE workspace_id = ? AND user_id = ?'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Exclusion:

    """One member excluded from creating times channels.

    Attributes:
        user_id: Slack user ID of the member.
        reason: Why the owner excluded the member.
        owner_id: Slack user ID of the owner who excluded the member.
        creation: When the member was excluded.
    """

    user_id: str
    reason: str
    owner_id: str
    creation: datetime.datetime

class ExclusionIO:

    """Reads and writes the members excluded from creating times channels in each workspace.

    Excluding a member leaves their times channel, if they have one, as it is.
    Each exclusion and its removal go into the history.
    """

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the exclusions.
        """

        self._database = database

    def load(
        self,
        workspace_id: str,
        user_id: str
    ) -> Exclusion | None:

        """Loads the exclusion of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.

        Returns:
            The exclusion, or None when the member is not excluded.
        """

        row = self._database.connect().execute(_EXCLUSION_SELECT, (workspace_id, user_id)).fetchone()

        return None if row is None else _decode(row)

    def find(
        self,
        workspace_id: str
    ) -> list[Exclusion]:

        """Finds the members excluded in a workspace.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The exclusions, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_WORKSPACE_SELECT, (workspace_id,))]

    def add(
        self,
        workspace_id: str,
        exclusion: Exclusion
    ) -> bool:

        """Excludes a member, unless they are excluded already.

        Args:
            workspace_id: Slack workspace ID.
            exclusion: The exclusion.

        Returns:
            Whether the member was excluded now, rather than already.
        """

        with self._database.begin() as connection:

            if connection.execute(_EXCLUSION_INSERT, (workspace_id, exclusion.user_id, exclusion.reason, exclusion.owner_id, exclusion.creation.isoformat())).rowcount != 1: return False

            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'exclude', actor_id = exclusion.owner_id, target_id = exclusion.user_id, details = {'reason': exclusion.reason}, creation = exclusion.creation))

            return True

    def remove(
        self,
        workspace_id: str,
        user_id: str,
        *,
        owner_id: str,
        now: datetime.datetime
    ) -> bool:

        """Lets an excluded member create times channels again.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            owner_id: Slack user ID of the owner who removes the exclusion.
            now: The current time.

        Returns:
            Whether the member was excluded until now.
        """

        with self._database.begin() as connection:

            if connection.execute(_EXCLUSION_DELETE, (workspace_id, user_id)).rowcount != 1: return False

            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'include', actor_id = owner_id, target_id = user_id, creation = now))

            return True

def _decode(
    row: sqlite3.Row
) -> Exclusion:

    return Exclusion(user_id = row['user_id'], reason = row['exclusion_reason'], owner_id = row['create_user'], creation = datetime.datetime.fromisoformat(row['create_time']))
