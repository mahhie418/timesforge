"""History of what changed about times channels and the rules for creating them."""

import dataclasses
import datetime
import json
import sqlite3
import typing

import timesforge.storage

type Action = typing.Literal['create', 'import', 'rename', 'archive', 'unarchive', 'delete', 'include', 'exclude', 'grant', 'revoke']

_ENTRY_INSERT = 'INSERT INTO history (workspace_id, actor_id, target_id, channel_id, history_action, detail_data, create_time) VALUES (?, ?, ?, ?, ?, ?, ?)'
_ENTRY_SELECT = 'SELECT actor_id, target_id, channel_id, history_action, detail_data, create_time FROM history WHERE workspace_id = ? ORDER BY entry_id DESC LIMIT ?'

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Entry:

    """One change in the history.

    Attributes:
        action: What changed.
        actor_id: Slack user ID of the user who made the change, or None when Slack does not tell.
        target_id: Slack user ID of the member whom the change concerns, or None.
        channel_id: Slack channel ID of the times channel that changed, or None.
        details: Further facts about the change, such as the new name of a channel.
        creation: When the change happened.
    """

    action: Action
    actor_id: str | None = None
    target_id: str | None = None
    channel_id: str | None = None
    details: dict[str, str] = dataclasses.field(default_factory = dict[str, str])
    creation: datetime.datetime

def record(
    connection: sqlite3.Connection,
    workspace_id: str,
    entry: Entry
) -> None:

    """Adds a change to the history.

    Args:
        connection: Connection to the database, inside the transaction that
                    makes the change, so that the history never misses it.
        workspace_id: Slack workspace ID.
        entry: The change.
    """

    connection.execute(_ENTRY_INSERT, (workspace_id, entry.actor_id, entry.target_id, entry.channel_id, entry.action, json.dumps(entry.details, ensure_ascii = False, sort_keys = True), entry.creation.isoformat()))

class HistoryIO:

    """Reads the history of each workspace."""

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the history.
        """

        self._database = database

    def load(
        self,
        workspace_id: str,
        limit: int
    ) -> list[Entry]:

        """Loads the latest changes of a workspace.

        Args:
            workspace_id: Slack workspace ID.
            limit: Most changes to load.

        Returns:
            The changes, newest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_ENTRY_SELECT, (workspace_id, limit))]

def _decode(
    row: sqlite3.Row
) -> Entry:

    return Entry(action = row['history_action'], actor_id = row['actor_id'], target_id = row['target_id'], channel_id = row['channel_id'], details = json.loads(row['detail_data']), creation = datetime.datetime.fromisoformat(row['create_time']))
