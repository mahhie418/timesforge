"""Rules that decide whether a member may create a times channel."""

import sqlite3
import typing

type Refusal = typing.Literal['holder', 'used']

_CHANNEL_COUNT = "SELECT count(*) AS total, count(*) FILTER (WHERE channel_status != 'deleted') AS current FROM channel WHERE workspace_id = ? AND holder_id = ?"

def decide(
    connection: sqlite3.Connection,
    workspace_id: str,
    user_id: str
) -> Refusal | None:

    """Decides whether a member may create a times channel now.

    Each member may create one times channel. Deleting it does not give the
    right back.

    Args:
        connection: Connection to the database. Inside a transaction of the
                    caller, the decision holds until the caller writes.
        workspace_id: Slack workspace ID.
        user_id: Slack user ID of the member.

    Returns:
        None when the member may create a times channel. Otherwise, why not:
        holder when they hold one that is not deleted, or used when theirs
        was deleted.
    """

    counts = connection.execute(_CHANNEL_COUNT, (workspace_id, user_id)).fetchone()

    if counts['current']: return 'holder'
    if counts['total']: return 'used'

    return None
