# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Invitations of workspace members to times channels, with the result for each member."""

import collections.abc
import dataclasses
import datetime
import sqlite3
import typing

import timesforge.storage

type Status = typing.Literal['invited', 'failed']

_CHANNEL_SELECT = 'SELECT user_id, invitation_status, attempt_count, error_message, update_time FROM invitation WHERE workspace_id = ? AND channel_id = ? ORDER BY user_id'

_INVITATION_UPSERT = """
    INSERT INTO invitation (workspace_id, channel_id, user_id, invitation_status, attempt_count, error_message, update_time)
    VALUES (?, ?, ?, ?, 1, ?, ?)
    ON CONFLICT (workspace_id, channel_id, user_id) DO UPDATE SET
        invitation_status = excluded.invitation_status,
        attempt_count = attempt_count + 1,
        error_message = excluded.error_message,
        update_time = excluded.update_time
"""

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Invitation:

    """The invitation of one member to one times channel.

    Attributes:
        user_id: Slack user ID of the member.
        status: invited once Slack added the member, or failed when Slack refused.
        attempt_count: Number of times the member was invited.
        error: Why Slack refused the last invitation, or None.
        update: When the member was last invited.
    """

    user_id: str
    status: Status
    attempt_count: int
    error: str | None = None
    update: datetime.datetime

class InvitationIO:

    """Reads and writes the invitations to the times channels of each workspace."""

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the invitations.
        """

        self._database = database

    def find(
        self,
        workspace_id: str,
        channel_id: str
    ) -> list[Invitation]:

        """Finds the invitations to a times channel.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.

        Returns:
            The invitations, by user ID.
        """

        return [_decode(row) for row in self._database.connect().execute(_CHANNEL_SELECT, (workspace_id, channel_id))]

    def record(
        self,
        workspace_id: str,
        channel_id: str,
        results: collections.abc.Mapping[str, str | None],
        now: datetime.datetime
    ) -> None:

        """Records the results of inviting members to a times channel.

        Args:
            workspace_id: Slack workspace ID.
            channel_id: Slack channel ID.
            results: Why Slack refused each member, or None for a member that Slack added, by user ID.
            now: When the members were invited.
        """

        with self._database.begin() as connection: connection.executemany(_INVITATION_UPSERT, [(workspace_id, channel_id, user_id, 'invited' if error is None else 'failed', error, now.isoformat()) for user_id, error in results.items()])

def _decode(
    row: sqlite3.Row
) -> Invitation:

    return Invitation(user_id = row['user_id'], status = row['invitation_status'], attempt_count = row['attempt_count'], error = row['error_message'], update = datetime.datetime.fromisoformat(row['update_time']))
