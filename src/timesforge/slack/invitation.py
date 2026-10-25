"""Invitations of the eligible members of the workspace to times channels."""

import collections.abc
import datetime
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.slack.api
import timesforge.times.invitation

BATCH_SIZE_MAXIMUM = 1000

_FLAGS_INELIGIBLE = ('deleted', 'is_bot', 'is_workflow_bot', 'is_restricted', 'is_ultra_restricted', 'is_invited_user', 'is_stranger')

def eligible(
    user: collections.abc.Mapping[str, typing.Any]
) -> bool:

    """Tells whether a user is invited to times channels.

    The primary owner, owners, admins and members are, unless they are
    deactivated or have not joined the workspace yet. Guests, bots, Slackbot
    and users of other organisations are not. Whether the owner excluded a
    member from creating times channels does not matter.

    Args:
        user: The user, as users.list returns it.

    Returns:
        Whether the user is invited.
    """

    return user.get('id') != 'USLACKBOT' and not any(user.get(flag) for flag in _FLAGS_INELIGIBLE)

class Inviter:

    """Invites the eligible members of one workspace to its times channels.

    The bot invites the members, so it joins a channel first when the user
    token of an admin created it. A member who is in the channel already is
    not invited again, so inviting again only retries the members whom Slack
    refused, and never creates the channel again.
    """

    def __init__(
        self,
        bot: slack_sdk.web.WebClient,
        writer: slack_sdk.web.WebClient,
        store: timesforge.times.invitation.InvitationIO,
        workspace_id: str
    ) -> None:

        """Initialises the inviter.

        Args:
            bot: Client with the bot token, which invites the members.
            writer: Client that created the channels, which invites the bot.
            store: Invitations of the workspace.
            workspace_id: Slack workspace ID.
        """

        self._bot = bot
        self._writer = writer
        self._store = store
        self._workspace_id = workspace_id

    def invite(
        self,
        channel_id: str,
        now: datetime.datetime
    ) -> list[str]:

        """Invites the eligible members who are not in a times channel yet.

        Args:
            channel_id: Slack channel ID.
            now: The current time.

        Returns:
            User IDs of the members whom Slack refused, in order.

        Raises:
            slack_sdk.errors.SlackApiError: Slack refused to tell the users or
                                            the members, or to add the bot.
        """

        identity = self._bot.auth_test().get('user_id', '')
        members = set(timesforge.slack.api.members(self._bot, channel_id))

        if identity not in members: self._writer.conversations_invite(channel = channel_id, users = identity)

        targets = [user['id'] for user in timesforge.slack.api.users(self._bot) if eligible(user) and user['id'] not in members | {identity}]
        results = {}

        for start in range(0, len(targets), BATCH_SIZE_MAXIMUM): results |= self._send(channel_id, targets[start:start + BATCH_SIZE_MAXIMUM])

        self._store.record(self._workspace_id, channel_id, results, now)

        return sorted(user for user, error in results.items() if error is not None)

    def _send(
        self,
        channel_id: str,
        users: list[str]
    ) -> dict[str, str | None]:

        try: response: slack_sdk.web.SlackResponse = self._bot.conversations_invite(channel = channel_id, users = ','.join(users), force = True)
        except slack_sdk.errors.SlackApiError as error: response = error.response

        entries = response.get('errors', [])
        errors = {entry['user']: entry['error'] for entry in entries}

        if not (response.get('ok') or errors): errors = dict.fromkeys(users, str(response.get('error')))

        return {user: errors.get(user) for user in users}
