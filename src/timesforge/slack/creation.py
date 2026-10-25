"""Creation of public times channels in Slack for the requests that timesforge reserved."""

import datetime
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.times.registry
import timesforge.times.request

class Creator:

    """Creates the times channels of the requests of one workspace in Slack.

    The member who asked holds the channel, whoever Slack records as its
    creator. When Slack has a channel with the name already, the request
    waits for the owner; when Slack refuses, it fails.
    """

    def __init__(
        self,
        writer: slack_sdk.web.WebClient,
        store: timesforge.times.request.RequestIO,
        workspace_id: str
    ) -> None:

        """Initialises the creator.

        Args:
            writer: Client that creates the channels: with the user token of
                    an admin where only admins may create channels, or else
                    with the bot token.
            store: Requests of the workspace.
            workspace_id: Slack workspace ID.
        """

        self._writer = writer
        self._store = store
        self._workspace_id = workspace_id

    def create(
        self,
        request_id: int,
        now: datetime.datetime
    ) -> timesforge.times.request.Request | None:

        """Creates the times channel of a reserved request.

        Nothing happens when the request is not reserved, such as when
        another caller creates its channel already.

        Args:
            request_id: ID of the request.
            now: The current time.

        Returns:
            The request afterwards, or None when it does not exist.
        """

        if (request := self._store.load(self._workspace_id, request_id)) is not None and self._store.start(self._workspace_id, request_id, now): self._attempt(request, now)

        return self._store.load(self._workspace_id, request_id)

    def _attempt(
        self,
        request: timesforge.times.request.Request,
        now: datetime.datetime
    ) -> None:

        try:

            channel: dict[str, typing.Any] = self._writer.conversations_create(name = request.channel_name, is_private = False).get('channel', {})

        except slack_sdk.errors.SlackApiError as error:

            response: slack_sdk.web.SlackResponse = error.response

            match response.get('error'):

                case 'name_taken': self._store.postpone(self._workspace_id, request.request_id, now)
                case code: self._store.fail(self._workspace_id, request.request_id, error = str(code), now = now)

            return

        self._finish(request, channel, now)

    def _finish(
        self,
        request: timesforge.times.request.Request,
        channel: dict[str, typing.Any],
        now: datetime.datetime
    ) -> None:

        registration = timesforge.times.registry.Channel(channel_id = channel['id'], holder_id = request.user_id, first_name = request.first_name, channel_name = channel['name'], creation = datetime.datetime.fromtimestamp(channel['created'], datetime.UTC))

        self._store.finish(self._workspace_id, request.request_id, registration, creator_id = channel.get('creator', ''), now = now)
