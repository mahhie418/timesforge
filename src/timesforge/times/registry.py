"""Times channels that timesforge knows, with the members who hold them."""

import dataclasses
import datetime
import sqlite3
import typing

import timesforge.storage
import timesforge.times.history

type Source = typing.Literal['created', 'imported']
type Status = typing.Literal['active', 'archived', 'deleted']

_CHANNEL_SELECT = 'SELECT channel_id, holder_id, first_name, channel_name, channel_source, channel_status, create_time, archive_time, delete_time FROM channel WHERE workspace_id = ? AND channel_id = ?'
_CURRENT_SELECT = "SELECT channel_id, holder_id, first_name, channel_name, channel_source, channel_status, create_time, archive_time, delete_time FROM channel WHERE workspace_id = ? AND channel_status != 'deleted' ORDER BY create_time"
_HOLDER_SELECT = 'SELECT channel_id, holder_id, first_name, channel_name, channel_source, channel_status, create_time, archive_time, delete_time FROM channel WHERE workspace_id = ? AND holder_id = ? ORDER BY create_time'
_CHANNEL_INSERT = 'INSERT INTO channel (workspace_id, channel_id, holder_id, first_name, channel_name, channel_source, channel_status, create_time, update_time, archive_time, delete_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
_CHANNEL_ARCHIVE = "UPDATE channel SET channel_status = 'archived', archive_time = ?, update_time = ? WHERE workspace_id = ? AND channel_id = ? AND channel_status = 'active' RETURNING holder_id"
_CHANNEL_UNARCHIVE = "UPDATE channel SET channel_status = 'active', archive_time = NULL, update_time = ? WHERE workspace_id = ? AND channel_id = ? AND channel_status = 'archived' RETURNING holder_id"
_CHANNEL_RENAME = "UPDATE channel SET channel_name = ?, update_time = ? WHERE workspace_id = ? AND channel_id = ? AND channel_status != 'deleted' AND channel_name != ? RETURNING holder_id"
_CHANNEL_REASSIGN = 'UPDATE channel SET holder_id = ?, update_time = ? WHERE workspace_id = ? AND channel_id = ?'
_CHANNEL_DELETE = "UPDATE channel SET channel_status = 'deleted', delete_time = ?, update_time = ? WHERE workspace_id = ? AND channel_id = ? AND channel_status != 'deleted' RETURNING holder_id"

class ChannelDuplicateError(Exception):

    """Raised when a times channel is registered twice, or for a member who holds one that is not deleted."""

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Channel:

    """One times channel.

    Attributes:
        channel_id: Slack channel ID.
        holder_id: Slack user ID of the member who holds the channel: the member who asked for it, whoever Slack records as its creator.
        first_name: First name that the holder entered.
        channel_name: Name of the channel, which follows renames in Slack.
        source: Whether timesforge created the channel, or imported one that the holder had created by hand.
        status: Whether the channel is in use (active), archived, or deleted in Slack.
        creation: When the channel was created.
        archival: When the channel was archived, or None while it is not archived.
        deletion: When the channel was deleted, or None while it exists.
    """

    channel_id: str
    holder_id: str
    first_name: str
    channel_name: str
    source: Source = 'created'
    status: Status = 'active'
    creation: datetime.datetime
    archival: datetime.datetime | None = None
    deletion: datetime.datetime | None = None

def insert(
    connection: sqlite3.Connection,
    workspace_id: str,
    channel: Channel
) -> None:

    """Registers a times channel in a transaction of the caller.

    Args:
        connection: Connection to the database, inside the transaction that
                    registers the channel.
        workspace_id: Slack workspace ID.
        channel: The channel.

    Raises:
        ChannelDuplicateError: The channel is registered already, or its
                               holder holds a times channel that is not deleted.
    """

    times = [None if moment is None else moment.isoformat() for moment in (channel.creation, channel.archival, channel.deletion)]

    try: connection.execute(_CHANNEL_INSERT, (workspace_id, channel.channel_id, channel.holder_id, channel.first_name, channel.channel_name, channel.source, channel.status, times[0], times[0], times[1], times[2]))
    except sqlite3.IntegrityError: raise ChannelDuplicateError(f'{channel.channel_id} is registered already, or {channel.holder_id} holds a times channel') from None

class RegistryIO:

    """Reads and writes the times channels of each workspace in the database.

    Archiving, restoring, renaming and deleting a channel in Slack change its
    record but never its holder, and each change goes into the history. A
    deleted channel stays deleted, so its record keeps the history of the
    holder. Slack may send the same event twice, so a change that a channel
    already has changes nothing.
    """

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the times channels.
        """

        self._database = database

    def load(
        self,
        workspace_id: str,
        channel_id: str
    ) -> Channel | None:

        """Loads a times channel.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.

        Returns:
            The channel, or None when it is not a times channel.
        """

        row = self._database.connect().execute(_CHANNEL_SELECT, (workspace_id, channel_id)).fetchone()

        return None if row is None else _decode(row)

    def find(
        self,
        workspace_id: str,
        holder_id: str
    ) -> list[Channel]:

        """Finds the times channels of a member.

        Args:
            workspace_id: Slack workspace ID.
            holder_id: Slack user ID of the member.

        Returns:
            The channels that the member holds or held, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_HOLDER_SELECT, (workspace_id, holder_id))]

    def scan(
        self,
        workspace_id: str
    ) -> list[Channel]:

        """Lists the times channels of a workspace that are not deleted.

        Args:
            workspace_id: Slack workspace ID.

        Returns:
            The channels in use or archived, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_CURRENT_SELECT, (workspace_id,))]

    def save(
        self,
        workspace_id: str,
        channel: Channel
    ) -> None:

        """Registers a times channel.

        Args:
            workspace_id: Slack workspace ID.
            channel: The channel.

        Raises:
            ChannelDuplicateError: The channel is registered already, or its
                                   holder holds a times channel that is not deleted.
        """

        with self._database.begin() as connection: insert(connection, workspace_id, channel)

    def archive(
        self,
        workspace_id: str,
        channel_id: str,
        now: datetime.datetime,
        *,
        actor_id: str | None = None
    ) -> bool:

        """Marks a times channel in use as archived.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            now: When the channel was archived.
            actor_id: Slack user ID of the user who archived the channel, or None when Slack does not tell.

        Returns:
            Whether the channel changed.
        """

        return self._update(_CHANNEL_ARCHIVE, (now.isoformat(), now.isoformat(), workspace_id, channel_id), workspace_id, timesforge.times.history.Entry(action = 'archive', actor_id = actor_id, channel_id = channel_id, creation = now))

    def unarchive(
        self,
        workspace_id: str,
        channel_id: str,
        now: datetime.datetime,
        *,
        actor_id: str | None = None
    ) -> bool:

        """Marks an archived times channel as in use again.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            now: When the channel was restored.
            actor_id: Slack user ID of the user who restored the channel, or None when Slack does not tell.

        Returns:
            Whether the channel changed.
        """

        return self._update(_CHANNEL_UNARCHIVE, (now.isoformat(), workspace_id, channel_id), workspace_id, timesforge.times.history.Entry(action = 'unarchive', actor_id = actor_id, channel_id = channel_id, creation = now))

    def rename(
        self,
        workspace_id: str,
        channel_id: str,
        channel_name: str,
        now: datetime.datetime,
        *,
        actor_id: str | None = None
    ) -> bool:

        """Records the new name of a times channel that is not deleted.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            channel_name: New name of the channel.
            now: When the channel was renamed.
            actor_id: Slack user ID of the user who renamed the channel, or None when Slack does not tell.

        Returns:
            Whether the channel changed.
        """

        return self._update(_CHANNEL_RENAME, (channel_name, now.isoformat(), workspace_id, channel_id, channel_name), workspace_id, timesforge.times.history.Entry(action = 'rename', actor_id = actor_id, channel_id = channel_id, details = {'channel_name': channel_name}, creation = now))

    def delete(
        self,
        workspace_id: str,
        channel_id: str,
        now: datetime.datetime,
        *,
        actor_id: str | None = None
    ) -> bool:

        """Marks a times channel as deleted, keeping its record.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            now: When the channel was deleted.
            actor_id: Slack user ID of the user who deleted the channel, or None when Slack does not tell.

        Returns:
            Whether the channel changed.
        """

        return self._update(_CHANNEL_DELETE, (now.isoformat(), now.isoformat(), workspace_id, channel_id), workspace_id, timesforge.times.history.Entry(action = 'delete', actor_id = actor_id, channel_id = channel_id, creation = now))

    def reassign(
        self,
        workspace_id: str,
        channel_id: str,
        holder_id: str,
        *,
        owner_id: str,
        now: datetime.datetime
    ) -> bool:

        """Gives a times channel another holder, as when the owner corrects the holder of an imported channel.

        The change goes into the history with the former holder.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            holder_id: Slack user ID of the new holder.
            owner_id: Slack user ID of the owner.
            now: The current time.

        Returns:
            Whether the holder changed; False when the channel is not a times
            channel, or the member holds it already.

        Raises:
            ChannelDuplicateError: The member holds another times channel that
                                   is not deleted, and this one is not deleted either.
        """

        with self._database.begin() as connection:

            if (row := connection.execute(_CHANNEL_SELECT, (workspace_id, channel_id)).fetchone()) is None or row['holder_id'] == holder_id: return False

            try: connection.execute(_CHANNEL_REASSIGN, (holder_id, now.isoformat(), workspace_id, channel_id))
            except sqlite3.IntegrityError: raise ChannelDuplicateError(f'{holder_id} holds a times channel') from None

            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'reassign', actor_id = owner_id, target_id = holder_id, channel_id = channel_id, details = {'holder': row['holder_id']}, creation = now))

            return True

    def _update(
        self,
        statement: str,
        parameters: tuple[str, ...],
        workspace_id: str,
        entry: timesforge.times.history.Entry
    ) -> bool:

        with self._database.begin() as connection:

            if (row := connection.execute(statement, parameters).fetchone()) is None: return False

            timesforge.times.history.record(connection, workspace_id, dataclasses.replace(entry, target_id = row['holder_id']))

            return True

def _decode(
    row: sqlite3.Row
) -> Channel:

    archival, deletion = (None if row[name] is None else datetime.datetime.fromisoformat(row[name]) for name in ('archive_time', 'delete_time'))

    return Channel(channel_id = row['channel_id'], holder_id = row['holder_id'], first_name = row['first_name'], channel_name = row['channel_name'], source = row['channel_source'], status = row['channel_status'], creation = datetime.datetime.fromisoformat(row['create_time']), archival = archival, deletion = deletion)
