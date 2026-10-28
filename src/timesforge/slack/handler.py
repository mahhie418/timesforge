"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import collections.abc
import datetime
import logging
import typing

import slack_bolt
import slack_sdk.errors

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.invitation
import timesforge.slack.permission
import timesforge.slack.reconciliation
import timesforge.slack.view
import timesforge.storage
import timesforge.times.naming
import timesforge.times.policy
import timesforge.times.registry
import timesforge.times.request

_LOGGER = logging.getLogger(__name__)

def register(
    application: slack_bolt.App,
    settings: timesforge.configuration.Settings,
    database: timesforge.storage.Database
) -> collections.abc.Callable[[str, datetime.datetime], None]:

    """Registers the listeners of the app.

    The listeners call Slack with the client of the app, which holds the bot
    token of the one workspace, rather than with a client per request. What
    a view shows depends on the role of its viewer, and each view is in the
    language of the Slack locale of its viewer.

    When a times channel is archived, restored, renamed or deleted in Slack,
    its record follows, and the App Home of its holder shows the change.
    Slack may send an event twice or out of order, so Slack is asked for the
    state of the channel rather than trusted with the event.

    A member who may create a times channel opens a modal from the App Home
    and enters the first name that names it. A first name that cannot name a
    times channel, a guest, or a member whom the rules do not let create one
    is refused in the modal. Otherwise the request is approved without the
    owner, which reserves the channel for the member, unless its name is
    taken: then it waits for the owner.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the times channels of each workspace.

    Returns:
        The function that brings the records of every times channel in line
        with Slack, for the changes made while the app was stopped, given the
        workspace ID and the current time.
    """

    registry = timesforge.times.registry.RegistryIO(database)
    requests = timesforge.times.request.RequestIO(database)

    def inspect(
        user: str
    ) -> tuple[bool, timesforge.configuration.Language]:

        entry = application.client.users_info(user = user, include_locale = True).get('user', {})

        return timesforge.slack.invitation.eligible(entry), timesforge.localisation.choose(entry.get('locale'), settings.timesforge_language_display)

    def choose(
        user: str
    ) -> timesforge.configuration.Language:

        return inspect(user)[1]

    def refresh(
        team: str,
        user: str
    ) -> None:

        refusal = timesforge.times.policy.decide(database.connect(), team, user)
        history = requests.find(team, user)
        eligible, language = inspect(user)

        application.client.views_publish(user_id = user, view = timesforge.slack.view.home(refusal = refusal, eligible = eligible, request = history[-1] if history else None, role = timesforge.slack.permission.role(settings, user), language = language))

    def reconcile(
        team: str,
        now: datetime.datetime,
        channel_ids: collections.abc.Collection[str] | None = None
    ) -> None:

        for channel_id in timesforge.slack.reconciliation.reconcile(application.client, registry, team, now, channel_ids):

            if (channel := registry.load(team, channel_id)) is not None: refresh(team, channel.holder_id)

    def recover(
        team: str,
        now: datetime.datetime
    ) -> None:

        try: reconcile(team, now)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Times channels were not reconciled: %s', error)

    def publish(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if event.get('tab') != 'home' or context.team_id is None: return

        refresh(context.team_id, event['user'])

    def follow(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if context.team_id is None: return

        channel = event['channel']

        reconcile(context.team_id, datetime.datetime.now(datetime.UTC), [channel if isinstance(channel, str) else channel['id']])

    def ask(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.collect(language = choose(context.user_id)))

    def reserve(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, user = context.team_id, context.user_id

        if team is None or user is None: return

        first_name = view['state']['values'][timesforge.slack.view.NAME_INPUT][timesforge.slack.view.NAME_INPUT]['value']
        eligible, language = inspect(user)

        if not eligible: ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('creation.refusal.ineligible', language)}); return

        try:

            request = requests.reserve(team, user, first_name, datetime.datetime.now(datetime.UTC))

        except timesforge.times.naming.NameInvalidError as error:

            ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate(f'creation.error.{error.reason}', language)})

            return

        except timesforge.times.request.RequestRefusedError as error:

            ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate(f'creation.refusal.{error.refusal}', language)})

            return

        ack(response_action = 'update', view = timesforge.slack.view.approve(request = request, language = language))
        refresh(team, user)

    application.event('app_home_opened')(publish)
    application.event('channel_archive')(follow)
    application.event('channel_deleted')(follow)
    application.event('channel_rename')(follow)
    application.event('channel_unarchive')(follow)
    application.action(timesforge.slack.view.CREATION_ACTION)(ask)
    application.view(timesforge.slack.view.CREATION_CALLBACK)(reserve)

    return recover
