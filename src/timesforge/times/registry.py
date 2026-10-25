"""Times channels that timesforge created, with the members who hold them."""

import dataclasses
import datetime
import sqlite3

import timesforge.storage

_CHANNEL_SELECT = 'SELECT channel_id, holder_id, first_name, channel_name, create_time FROM channel WHERE workspace_id = ? AND channel_id = ?'
_HOLDER_SELECT = 'SELECT channel_id, holder_id, first_name, channel_name, create_time FROM channel WHERE workspace_id = ? AND holder_id = ? ORDER BY create_time'
_CHANNEL_INSERT = 'INSERT INTO channel (workspace_id, channel_id, holder_id, first_name, channel_name, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Channel:

    """One times channel.

    Attributes:
        channel_id: Slack channel ID.
        holder_id: Slack user ID of the member who holds the channel: the member who asked for it, whoever Slack records as its creator.
        first_name: First name that the holder entered.
        channel_name: Name of the channel.
        creation: When the channel was created.
    """

    channel_id: str
    holder_id: str
    first_name: str
    channel_name: str
    creation: datetime.datetime

class RegistryIO:

    """Reads and writes the times channels of each workspace in the database."""

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

    def save(
        self,
        workspace_id: str,
        channel: Channel
    ) -> None:

        """Registers a times channel.

        Args:
            workspace_id: Slack workspace ID.
            channel: The channel.
        """

        creation = channel.creation.isoformat()

        with self._database.begin() as connection: connection.execute(_CHANNEL_INSERT, (workspace_id, channel.channel_id, channel.holder_id, channel.first_name, channel.channel_name, creation, creation))

def _decode(
    row: sqlite3.Row
) -> Channel:

    return Channel(channel_id = row['channel_id'], holder_id = row['holder_id'], first_name = row['first_name'], channel_name = row['channel_name'], creation = datetime.datetime.fromisoformat(row['create_time']))
