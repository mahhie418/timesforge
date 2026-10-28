"""Messages that welcome new members and tell them how to create their times channels."""

import collections.abc
import dataclasses
import datetime
import json
import sqlite3
import typing

import timesforge.storage

type Status = typing.Literal['pending', 'sending', 'sent', 'failed', 'unknown']

_MESSAGE_SELECT = 'SELECT user_id, channel_id, event_id, message_status, conversation_id, message_ts, error_message, create_time, send_time FROM onboarding WHERE workspace_id = ? AND user_id = ?'
_STATUS_SELECT = 'SELECT user_id, channel_id, event_id, message_status, conversation_id, message_ts, error_message, create_time, send_time FROM onboarding WHERE workspace_id = ? AND message_status IN (SELECT value FROM json_each(?)) ORDER BY create_time, user_id'
_MESSAGE_INSERT = "INSERT INTO onboarding (workspace_id, user_id, channel_id, event_id, message_status, create_time, update_time) VALUES (?, ?, ?, ?, 'pending', ?, ?) ON CONFLICT (workspace_id, user_id) DO NOTHING"
_MESSAGE_SEND = "UPDATE onboarding SET message_status = 'sending', error_message = NULL, update_time = ? WHERE workspace_id = ? AND user_id = ? AND message_status IN ('pending', 'failed')"
_MESSAGE_SUCCEED = "UPDATE onboarding SET message_status = 'sent', conversation_id = ?, message_ts = ?, error_message = NULL, send_time = ?, update_time = ? WHERE workspace_id = ? AND user_id = ? AND message_status IN ('sending', 'unknown')"
_MESSAGE_FAIL = "UPDATE onboarding SET message_status = 'failed', error_message = ?, update_time = ? WHERE workspace_id = ? AND user_id = ? AND message_status = 'sending'"
_MESSAGE_LOSE = "UPDATE onboarding SET message_status = 'unknown', error_message = ?, update_time = ? WHERE workspace_id = ? AND user_id = ? AND message_status = 'sending'"

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Message:

    """The welcome message of one member.

    Attributes:
        user_id: Slack user ID of the member.
        channel_id: Slack channel ID of the channel whose joining started the message, such as #welcome.
        event_id: ID of the Slack event that started the message.
        status: pending until it is sent, sending while it is sent, sent once Slack took it, failed when Slack refused it, or unknown when nobody knows whether Slack took it.
        conversation_id: Slack ID of the direct message conversation, or None until the message is sent.
        message_ts: Timestamp of the message, or None until it is sent.
        error: Why the last attempt failed or was lost, or None.
        creation: When the member joined.
        delivery: When the message was sent, or None until it is.
    """

    user_id: str
    channel_id: str
    event_id: str
    status: Status
    conversation_id: str | None = None
    message_ts: str | None = None
    error: str | None = None
    creation: datetime.datetime
    delivery: datetime.datetime | None = None

class OnboardingIO:

    """Reads and writes the welcome messages of each workspace.

    Each member gets at most one welcome message, whatever Slack sends again
    and however often the member leaves and joins, even across restarts.
    A message whose result is unknown is never sent again on its own, so
    that no member gets two.
    """

    def __init__(
        self,
        database: timesforge.storage.Database
    ) -> None:

        """Initialises the store.

        Args:
            database: The database that holds the welcome messages.
        """

        self._database = database

    def load(
        self,
        workspace_id: str,
        user_id: str
    ) -> Message | None:

        """Loads the welcome message of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.

        Returns:
            The message, or None when the member was never welcomed.
        """

        row = self._database.connect().execute(_MESSAGE_SELECT, (workspace_id, user_id)).fetchone()

        return None if row is None else _decode(row)

    def scan(
        self,
        workspace_id: str,
        statuses: collections.abc.Collection[Status]
    ) -> list[Message]:

        """Lists the welcome messages of a workspace in some statuses.

        Args:
            workspace_id: Slack workspace ID.
            statuses: The statuses.

        Returns:
            The messages, oldest first.
        """

        return [_decode(row) for row in self._database.connect().execute(_STATUS_SELECT, (workspace_id, json.dumps(sorted(statuses))))]

    def claim(
        self,
        workspace_id: str,
        user_id: str,
        *,
        channel_id: str,
        event_id: str,
        now: datetime.datetime
    ) -> bool:

        """Takes the welcome of a member for one event, before any message is sent.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            channel_id: Slack channel ID of the channel that the member joined.
            event_id: ID of the Slack event.
            now: When the member joined.

        Returns:
            Whether this event took the welcome; False when an earlier one did.
        """

        with self._database.begin() as connection: return connection.execute(_MESSAGE_INSERT, (workspace_id, user_id, channel_id, event_id, now.isoformat(), now.isoformat())).rowcount == 1

    def send(
        self,
        workspace_id: str,
        user_id: str,
        now: datetime.datetime
    ) -> bool:

        """Marks the welcome message of a member as being sent.

        Only a pending message, or one that Slack refused, may be sent.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            now: The current time.

        Returns:
            Whether the message may be sent now.
        """

        with self._database.begin() as connection: return connection.execute(_MESSAGE_SEND, (now.isoformat(), workspace_id, user_id)).rowcount == 1

    def succeed(
        self,
        workspace_id: str,
        user_id: str,
        *,
        conversation_id: str,
        message_ts: str,
        now: datetime.datetime
    ) -> bool:

        """Records that Slack took the welcome message of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            conversation_id: Slack ID of the direct message conversation.
            message_ts: Timestamp of the message.
            now: When the message was sent.

        Returns:
            Whether the message was being sent, or its result was unknown.
        """

        with self._database.begin() as connection: return connection.execute(_MESSAGE_SUCCEED, (conversation_id, message_ts, now.isoformat(), now.isoformat(), workspace_id, user_id)).rowcount == 1

    def fail(
        self,
        workspace_id: str,
        user_id: str,
        *,
        error: str,
        now: datetime.datetime
    ) -> bool:

        """Records that Slack refused the welcome message of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            error: Why Slack refused the message.
            now: The current time.

        Returns:
            Whether the message was being sent.
        """

        with self._database.begin() as connection: return connection.execute(_MESSAGE_FAIL, (error, now.isoformat(), workspace_id, user_id)).rowcount == 1

    def lose(
        self,
        workspace_id: str,
        user_id: str,
        *,
        error: str,
        now: datetime.datetime
    ) -> bool:

        """Records that nobody knows whether Slack took the welcome message of a member.

        Args:
            workspace_id: Slack workspace ID.
            user_id: Slack user ID of the member.
            error: What went wrong, such as a timeout.
            now: The current time.

        Returns:
            Whether the message was being sent.
        """

        with self._database.begin() as connection: return connection.execute(_MESSAGE_LOSE, (error, now.isoformat(), workspace_id, user_id)).rowcount == 1

def _decode(
    row: sqlite3.Row
) -> Message:

    delivery = None if row['send_time'] is None else datetime.datetime.fromisoformat(row['send_time'])

    return Message(user_id = row['user_id'], channel_id = row['channel_id'], event_id = row['event_id'], status = row['message_status'], conversation_id = row['conversation_id'], message_ts = row['message_ts'], error = row['error_message'], creation = datetime.datetime.fromisoformat(row['create_time']), delivery = delivery)
