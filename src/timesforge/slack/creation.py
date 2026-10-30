"""Creation of public times channels in Slack for the requests that TimesForge reserved."""

import datetime
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.slack.api
import timesforge.slack.invitation
import timesforge.times.registry
import timesforge.times.request

STATUS_SERVER_MINIMUM = 500

CREATION_MARGIN = datetime.timedelta(minutes = 1)

class Creator:

    """Creates the times channels of the requests of one workspace in Slack.

    The member who asked holds the channel, whoever Slack records as its
    creator. When Slack has a channel with the name already, the request
    waits for the owner; when Slack refuses, it fails. When nobody knows
    whether Slack created the channel, because the connection broke or Slack
    failed, the channel is looked for before it is created once more, so that
    no request ever creates two channels. Once the channel exists, the
    eligible members of the workspace are invited to it.
    """

    def __init__(
        self,
        writer: slack_sdk.web.WebClient,
        reader: slack_sdk.web.WebClient,
        store: timesforge.times.request.RequestIO,
        workspace_id: str,
        inviter: timesforge.slack.invitation.Inviter
    ) -> None:

        """Initialises the creator.

        Args:
            writer: Client that creates the channels and sends no request
                    twice (see `timesforge.slack.api.connect`): with the user
                    token of an admin where only admins may create channels,
                    or else with the bot token.
            reader: Client with the bot token, which reads the channels.
            store: Requests of the workspace.
            workspace_id: Slack workspace ID.
            inviter: Inviter of the members to the channels.
        """

        self._writer = writer
        self._reader = reader
        self._store = store
        self._workspace_id = workspace_id
        self._inviter = inviter

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

        if (request := self._store.load(self._workspace_id, request_id)) is not None and self._store.start(self._workspace_id, request_id, now): self._attempt(request, now, again = True)

        return self._store.load(self._workspace_id, request_id)

    def reconcile(
        self,
        request_id: int,
        now: datetime.datetime
    ) -> timesforge.times.request.Request | None:

        """Settles a request whose result is unknown.

        Slack is asked for a public channel with the name of the request that
        the creating user made since the request. When there is one, it is
        registered; otherwise the channel is created once more, now that it
        is known not to exist.

        Args:
            request_id: ID of the request.
            now: The current time.

        Returns:
            The request afterwards, or None when it does not exist.
        """

        if (request := self._store.load(self._workspace_id, request_id)) is None or request.status != 'reconciling': return request
        if (channel := self._find(request)) is not None: self._finish(request, channel, now); return self._store.load(self._workspace_id, request_id)
        if self._store.retry(self._workspace_id, request_id, now): self._attempt(request, now, again = False)

        return self._store.load(self._workspace_id, request_id)

    def resume(
        self,
        request_id: int,
        now: datetime.datetime
    ) -> timesforge.times.request.Request | None:

        """Takes up a request that the app left unfinished when it stopped.

        A reserved request is created, and one whose result is unknown is
        settled, as `reconcile` does. Once its channel exists, the members are
        invited, except those in the channel already. A request being created
        is left alone, because another caller may be creating it now; one that
        the app left being created must be marked as unknown first.

        Args:
            request_id: ID of the request.
            now: The current time.

        Returns:
            The request afterwards, or None when it does not exist.
        """

        match request := self._store.load(self._workspace_id, request_id):

            case timesforge.times.request.Request(status = 'reserved'): return self.create(request_id, now)
            case timesforge.times.request.Request(status = 'reconciling'): return self.reconcile(request_id, now)
            case timesforge.times.request.Request(status = 'created' | 'inviting' as status, channel_id = str() as channel_id):

                if status == 'inviting' or self._store.advance(self._workspace_id, request_id, now): self._invite(request_id, channel_id, now)

                return self._store.load(self._workspace_id, request_id)

            case _: return request

    def _attempt(
        self,
        request: timesforge.times.request.Request,
        now: datetime.datetime,
        *,
        again: bool
    ) -> None:

        try:

            channel: dict[str, typing.Any] = self._writer.conversations_create(name = request.channel_name, is_private = False).get('channel', {})

        except slack_sdk.errors.SlackApiError as error:

            response: slack_sdk.web.SlackResponse = error.response

            match response.get('error'):

                case _ if response.status_code >= STATUS_SERVER_MINIMUM: self._lose(request, f'Slack answered {response.status_code}', now, again = again)
                case 'name_taken': self._store.postpone(self._workspace_id, request.request_id, now)
                case code: self._store.fail(self._workspace_id, request.request_id, error = str(code), now = now)

            return

        except OSError as error:

            self._lose(request, str(error) or type(error).__name__, now, again = again)

            return

        self._finish(request, channel, now)

    def _lose(
        self,
        request: timesforge.times.request.Request,
        error: str,
        now: datetime.datetime,
        *,
        again: bool
    ) -> None:

        self._store.lose(self._workspace_id, request.request_id, error = error, now = now)

        if again: self.reconcile(request.request_id, now)

    def _find(
        self,
        request: timesforge.times.request.Request
    ) -> dict[str, typing.Any] | None:

        creator = self._writer.auth_test().get('user_id')
        earliest = (request.creation - CREATION_MARGIN).timestamp()

        return next((channel for channel in timesforge.slack.api.channels(self._reader) if channel['name'] == request.channel_name and channel.get('creator') == creator and channel['created'] >= earliest), None)

    def _finish(
        self,
        request: timesforge.times.request.Request,
        channel: dict[str, typing.Any],
        now: datetime.datetime
    ) -> None:

        registration = timesforge.times.registry.Channel(channel_id = channel['id'], holder_id = request.user_id, first_name = request.first_name, channel_name = channel['name'], creation = datetime.datetime.fromtimestamp(channel['created'], datetime.UTC))

        if not self._store.finish(self._workspace_id, request.request_id, registration, creator_id = channel.get('creator', ''), now = now): return
        if self._store.advance(self._workspace_id, request.request_id, now): self._invite(request.request_id, registration.channel_id, now)

    def _invite(
        self,
        request_id: int,
        channel_id: str,
        now: datetime.datetime
    ) -> None:

        self._inviter.invite(channel_id, now)
        self._store.complete(self._workspace_id, request_id, now)
