"""Welcome messages that the bot sends new members by direct message, once each."""

import datetime
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.times.onboarding

STATUS_SERVER_MINIMUM = 500

METADATA_TYPE = 'timesforge_welcome'

SENDING_MARGIN = datetime.timedelta(minutes = 1)

class Greeter:

    """Welcomes the new members of one workspace by direct message from the bot.

    A message is claimed before it is sent, so that an event that Slack sends
    again, or a member who leaves and joins again, sends nothing more, even
    across restarts. When nobody knows whether Slack took a message, because
    the connection broke or Slack failed, it is not sent again; `recover`
    looks for it in the direct message conversation instead, by the metadata
    that each welcome message carries.
    """

    def __init__(
        self,
        client: slack_sdk.web.WebClient,
        sender: slack_sdk.web.WebClient,
        store: timesforge.times.onboarding.OnboardingIO,
        workspace_id: str
    ) -> None:

        """Initialises the greeter.

        Args:
            client: Client with the bot token, which opens and reads the conversations.
            sender: Client with the bot token that sends no request twice (see
                    `timesforge.slack.api.connect`), which sends the messages.
            store: Welcome messages of the workspace.
            workspace_id: Slack workspace ID.
        """

        self._client = client
        self._sender = sender
        self._store = store
        self._workspace_id = workspace_id

    def greet(
        self,
        user_id: str,
        *,
        channel_id: str,
        event_id: str,
        text: str,
        blocks: list[dict[str, typing.Any]],
        now: datetime.datetime
    ) -> timesforge.times.onboarding.Message | None:

        """Welcomes a member, unless they were welcomed already.

        A message that Slack refused is sent again; one that was sent, or whose
        result is unknown, is not.

        Args:
            user_id: Slack user ID of the member.
            channel_id: Slack channel ID of the channel that the member joined.
            event_id: ID of the Slack event of the joining.
            text: Text of the message, for notifications.
            blocks: Blocks of the message.
            now: The current time.

        Returns:
            The message afterwards.
        """

        self._store.claim(self._workspace_id, user_id, channel_id = channel_id, event_id = event_id, now = now)

        if self._store.send(self._workspace_id, user_id, now): self._send(user_id, text, blocks, now)

        return self._store.load(self._workspace_id, user_id)

    def recover(
        self,
        user_id: str,
        now: datetime.datetime
    ) -> timesforge.times.onboarding.Message | None:

        """Looks for a welcome message whose result is unknown, and records it when Slack has it.

        A message that Slack does not have stays unknown, because Slack may
        still deliver it, so that no member gets two.

        Args:
            user_id: Slack user ID of the member.
            now: The current time.

        Returns:
            The message afterwards, or None when the member was never welcomed.

        Raises:
            slack_sdk.errors.SlackApiError: Slack refused to open or read the conversation.
        """

        if (message := self._store.load(self._workspace_id, user_id)) is None or message.status != 'unknown': return message

        conversation = self._client.conversations_open(users = user_id).get('channel', {})
        entries = self._client.conversations_history(channel = conversation['id'], oldest = str((message.creation - SENDING_MARGIN).timestamp()), include_all_metadata = True).get('messages', [])

        if (entry := next((entry for entry in entries if entry.get('metadata', {}).get('event_type') == METADATA_TYPE), None)) is not None: self._store.succeed(self._workspace_id, user_id, conversation_id = conversation['id'], message_ts = entry['ts'], now = now)

        return self._store.load(self._workspace_id, user_id)

    def _send(
        self,
        user_id: str,
        text: str,
        blocks: list[dict[str, typing.Any]],
        now: datetime.datetime
    ) -> None:

        try:

            conversation = self._client.conversations_open(users = user_id).get('channel', {})

        except (slack_sdk.errors.SlackApiError, OSError) as error:

            self._store.fail(self._workspace_id, user_id, error = str(error.response.get('error')) if isinstance(error, slack_sdk.errors.SlackApiError) else str(error) or type(error).__name__, now = now)

            return

        try:

            response = self._sender.chat_postMessage(channel = conversation['id'], text = text, blocks = blocks, metadata = {'event_type': METADATA_TYPE, 'event_payload': {'user_id': user_id}})

        except slack_sdk.errors.SlackApiError as error:

            failure: slack_sdk.web.SlackResponse = error.response

            if failure.status_code >= STATUS_SERVER_MINIMUM: self._store.lose(self._workspace_id, user_id, error = f'Slack answered {failure.status_code}', now = now)
            else: self._store.fail(self._workspace_id, user_id, error = str(failure.get('error')), now = now)

            return

        except OSError as error:

            self._store.lose(self._workspace_id, user_id, error = str(error) or type(error).__name__, now = now)

            return

        self._store.succeed(self._workspace_id, user_id, conversation_id = conversation['id'], message_ts = response.get('ts', ''), now = now)
