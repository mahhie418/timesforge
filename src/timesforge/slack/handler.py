"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import collections.abc
import datetime
import logging
import threading
import typing

import slack_bolt
import slack_sdk
import slack_sdk.errors

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.creation
import timesforge.slack.invitation
import timesforge.slack.permission
import timesforge.slack.reconciliation
import timesforge.slack.view
import timesforge.slack.welcome
import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.history
import timesforge.times.invitation
import timesforge.times.naming
import timesforge.times.onboarding
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

HISTORY_LIMIT = 50

_LOGGER = logging.getLogger(__name__)

def register(
    application: slack_bolt.App,
    settings: timesforge.configuration.Settings,
    database: timesforge.storage.Database,
    writer: slack_sdk.web.WebClient,
    sender: slack_sdk.web.WebClient
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
    taken: then it waits for the owner. The channel of an approved request is
    created in the background, as `timesforge.slack.creation.Creator` does,
    and the modal and the App Home of the member show how it ended. The
    requests that the app left unfinished when it stopped are taken up in the
    background once it starts again, and a channel that it was creating then
    is looked for in Slack before it is created once more.

    Only the owner chooses another name for a request whose name is taken,
    excludes members from creating times channels and lets them create one
    again, and gives and revokes recreation grants, as
    `timesforge.slack.permission.restrict` makes sure. A request with the
    name that the owner chose is created as an approved one is, for the
    member who asked. Excluding a member withdraws their request that waits
    to be created or for the owner, and the App Home of the member shows
    each change. The owner also reviews the holders of the imported times
    channels and corrects them, and reads the latest `HISTORY_LIMIT` changes
    in the history.

    A member who joins the channel in TIMESFORGE_CHANNEL_ID_WELCOME, such as
    #welcome, gets one direct message from the bot that tells them how to
    create their times channel and links to the App Home, as
    `timesforge.slack.welcome.Greeter` makes sure, unless they are a guest,
    are excluded, or have ever asked for or held a times channel. The
    messages whose results the app left unknown when it stopped are looked
    for in the background once it starts again. Once the member has a times
    channel, their welcome message is edited to link to it and no longer to
    ask them to create one; when Slack refuses the edit, the channel stays.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the times channels of each workspace.
        writer: Slack client that creates the times channels and sends no
                request twice (see `timesforge.slack.api.connect`): with the
                user token of an admin, or else with the bot token.
        sender: Slack client with the bot token that sends the welcome
                messages and sends no request twice.

    Returns:
        The function that catches up with what happened while the app was
        stopped, given the workspace ID and the current time: it brings the
        records of every times channel in line with Slack, takes up the
        unfinished requests, and looks for the welcome messages whose results
        are unknown. It must run before the app connects, while no listener
        can start a request or a message.
    """

    registry = timesforge.times.registry.RegistryIO(database)
    requests = timesforge.times.request.RequestIO(database)
    invitations = timesforge.times.invitation.InvitationIO(database)
    exclusions = timesforge.times.exclusion.ExclusionIO(database)
    recreations = timesforge.times.recreation.RecreationIO(database)
    log = timesforge.times.history.HistoryIO(database)
    onboarding = timesforge.times.onboarding.OnboardingIO(database)
    guard = [timesforge.slack.permission.restrict(settings)]

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
        role = timesforge.slack.permission.role(settings, user)

        application.client.views_publish(user_id = user, view = timesforge.slack.view.home(refusal = refusal, eligible = eligible, request = history[-1] if history else None, channels = registry.find(team, user), exclusions = exclusions.find(team) if role == 'owner' else [], grants = recreations.scan(team) if role == 'owner' else [], conflicts = requests.scan(team, ['pending_name_resolution']) if role == 'owner' else [], role = role, language = language))

    def show(
        modal: str,
        view: dict[str, typing.Any]
    ) -> None:

        try: application.client.views_update(view_id = modal, view = view)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Modal not updated, perhaps because it was closed: %s', error)

    def build(
        team: str
    ) -> timesforge.slack.creation.Creator:

        return timesforge.slack.creation.Creator(writer, application.client, requests, team, timesforge.slack.invitation.Inviter(application.client, writer, invitations, team))

    def notify(
        team: str,
        user: str
    ) -> None:

        current = next((channel for channel in registry.find(team, user) if channel.status != 'deleted'), None)

        if current is None or onboarding.load(team, user) is None: return

        text, blocks = timesforge.slack.view.ready(channel_id = current.channel_id, language = choose(user))

        try: timesforge.slack.welcome.Greeter(application.client, sender, onboarding, team).update(user, text = text, blocks = blocks, now = datetime.datetime.now(datetime.UTC))
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Welcome message of %s was not updated: %s', user, error)

    def create(
        team: str,
        user: str,
        request_id: int,
        modal: str,
        language: timesforge.configuration.Language
    ) -> None:

        try: build(team).create(request_id, datetime.datetime.now(datetime.UTC))
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Times channel of request %s was not finished: %s', request_id, error)

        refresh(team, user)
        notify(team, user)

        if (request := requests.load(team, request_id)) is not None: show(modal, timesforge.slack.view.report(request = request, language = language))

    def resume(
        team: str,
        request_ids: list[int]
    ) -> None:

        for request_id in request_ids:

            try: build(team).resume(request_id, datetime.datetime.now(datetime.UTC))
            except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Times channel of request %s was not finished: %s', request_id, error)

            if (request := requests.load(team, request_id)) is None: continue

            refresh(team, request.user_id)
            notify(team, request.user_id)

    def retrieve(
        team: str,
        users: list[str]
    ) -> None:

        for user in users:

            try: timesforge.slack.welcome.Greeter(application.client, sender, onboarding, team).recover(user, datetime.datetime.now(datetime.UTC))
            except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Welcome message of %s was not looked for: %s', user, error)

            notify(team, user)

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

        for request in requests.scan(team, ['creating']): requests.lose(team, request.request_id, error = 'interrupted', now = now)

        unfinished = [request.request_id for request in requests.scan(team, ['reserved', 'reconciling', 'created', 'inviting'])]

        for message in onboarding.scan(team, ['sending']): onboarding.lose(team, message.user_id, error = 'interrupted', now = now)

        unknown = [message.user_id for message in onboarding.scan(team, ['unknown'])]

        try: reconcile(team, now)
        except slack_sdk.errors.SlackApiError as error: _LOGGER.warning('Times channels were not reconciled: %s', error)

        if unfinished: detach(lambda: resume(team, unfinished))
        if unknown: detach(lambda: retrieve(team, unknown))

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

    def welcome(
        body: dict[str, typing.Any],
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, user = context.team_id, event['user']

        if team is None or event.get('channel') != settings.timesforge_channel_id_welcome: return

        eligible, language = inspect(user)

        if not eligible or registry.find(team, user) or requests.find(team, user) or exclusions.load(team, user) is not None: return

        text, blocks = timesforge.slack.view.welcome(workspace = application.client.auth_test().get('team', ''), team_id = team, app_id = body.get('api_app_id', ''), language = language)

        timesforge.slack.welcome.Greeter(application.client, sender, onboarding, team).greet(user, channel_id = event['channel'], event_id = body.get('event_id', ''), text = text, blocks = blocks, now = datetime.datetime.now(datetime.UTC))

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

        if request.status == 'reserved': detach(lambda: create(team, user, request.request_id, view['id'], language))

    def consider(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        request = requests.load(context.team_id, int(body['actions'][0]['value']))

        if request is None or request.status != 'pending_name_resolution': refresh(context.team_id, context.user_id); return

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.resolve(request = request, language = choose(context.user_id)))

    def resolve(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        name = view['state']['values'][timesforge.slack.view.NAME_INPUT][timesforge.slack.view.NAME_INPUT]['value']
        language = choose(owner)

        try:

            request = requests.resolve(team, int(view['private_metadata']), name, owner_id = owner, now = datetime.datetime.now(datetime.UTC))

        except timesforge.times.naming.NameInvalidError as error:

            ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate(f'creation.error.{error.reason}', language)})

            return

        except timesforge.times.request.NameTakenError:

            ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('resolution.error.taken', language)})

            return

        if request is None: ack(response_action = 'errors', errors = {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('resolution.error.settled', language)}); return

        member, request_id = request.user_id, request.request_id

        ack(response_action = 'update', view = timesforge.slack.view.approve(request = request, language = language))
        refresh(team, owner)
        detach(lambda: create(team, member, request_id, view['id'], language))

    def manage(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.exclude(exclusions = exclusions.find(context.team_id), language = choose(context.user_id)))

    def exclude(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        values = view['state']['values']
        user = values[timesforge.slack.view.MEMBER_INPUT][timesforge.slack.view.MEMBER_INPUT]['selected_user']
        choice = values[timesforge.slack.view.CHOICE_INPUT][timesforge.slack.view.CHOICE_INPUT]['selected_option']['value']
        reason = values[timesforge.slack.view.REASON_INPUT][timesforge.slack.view.REASON_INPUT].get('value') or ''
        language, now = choose(owner), datetime.datetime.now(datetime.UTC)

        if choice == 'exclude' and not reason.strip(): ack(response_action = 'errors', errors = {timesforge.slack.view.REASON_INPUT: timesforge.localisation.translate('exclusion.error.reason', language)}); return

        if choice == 'exclude': changed = exclusions.add(team, timesforge.times.exclusion.Exclusion(user_id = user, reason = reason.strip(), owner_id = owner, creation = now))
        else: changed = exclusions.remove(team, user, owner_id = owner, now = now)

        if not changed: ack(response_action = 'errors', errors = {timesforge.slack.view.MEMBER_INPUT: timesforge.localisation.translate(f'exclusion.error.{choice}', language)}); return
        if choice == 'exclude': requests.withdraw(team, user, error = 'excluded', now = now)

        ack()

        for person in dict.fromkeys([owner, user]): refresh(team, person)

    def offer(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.grant(grants = recreations.scan(context.team_id), language = choose(context.user_id)))

    def grant(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        values = view['state']['values']
        user = values[timesforge.slack.view.MEMBER_INPUT][timesforge.slack.view.MEMBER_INPUT]['selected_user']
        choice = values[timesforge.slack.view.CHOICE_INPUT][timesforge.slack.view.CHOICE_INPUT]['selected_option']['value']
        language, now = choose(owner), datetime.datetime.now(datetime.UTC)

        reason = None

        try:

            if choice == 'grant': recreations.grant(team, user, owner_id = owner, now = now)
            elif not recreations.revoke(team, user, owner_id = owner, now = now): reason = 'revoke'

        except timesforge.times.recreation.GrantInvalidError as error:

            reason = error.reason

        if reason is not None: ack(response_action = 'errors', errors = {timesforge.slack.view.MEMBER_INPUT: timesforge.localisation.translate(f'recreation.error.{reason}', language)}); return

        ack()

        for person in dict.fromkeys([owner, user]): refresh(team, person)

    def inquire(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        channels = [channel for channel in registry.scan(context.team_id) if channel.source == 'imported']

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.review(channels = channels, language = choose(context.user_id)))

    def reassign(
        ack: slack_bolt.Ack,
        view: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        team, owner = context.team_id, context.user_id

        if team is None or owner is None: return

        values = view['state']['values']
        channel_id = values[timesforge.slack.view.CHANNEL_INPUT][timesforge.slack.view.CHANNEL_INPUT]['selected_option']['value']
        holder = values[timesforge.slack.view.MEMBER_INPUT][timesforge.slack.view.MEMBER_INPUT]['selected_user']
        former = registry.load(team, channel_id)
        language = choose(owner)
        key = None if inspect(holder)[0] else 'review.error.ineligible'

        try:

            if key is None and not registry.reassign(team, channel_id, holder, owner_id = owner, now = datetime.datetime.now(datetime.UTC)): key = 'review.error.unchanged'

        except timesforge.times.registry.ChannelDuplicateError:

            key = 'review.error.held'

        if key is not None: ack(response_action = 'errors', errors = {timesforge.slack.view.MEMBER_INPUT: timesforge.localisation.translate(key, language)}); return

        ack()

        for person in dict.fromkeys([owner, holder] + ([former.holder_id] if former else [])): refresh(team, person)

    def retrace(
        ack: slack_bolt.Ack,
        body: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        ack()

        if context.team_id is None or context.user_id is None: return

        application.client.views_open(trigger_id = body['trigger_id'], view = timesforge.slack.view.trace(entries = log.load(context.team_id, HISTORY_LIMIT), language = choose(context.user_id)))

    application.event('app_home_opened')(publish)
    application.event('channel_archive')(follow)
    application.event('channel_deleted')(follow)
    application.event('channel_rename')(follow)
    application.event('channel_unarchive')(follow)
    application.event('member_joined_channel')(welcome)
    application.action(timesforge.slack.view.CREATION_ACTION)(ask)
    application.view(timesforge.slack.view.CREATION_CALLBACK)(reserve)
    application.action(timesforge.slack.view.RESOLUTION_ACTION, middleware = guard)(consider)
    application.view(timesforge.slack.view.RESOLUTION_CALLBACK, middleware = guard)(resolve)
    application.action(timesforge.slack.view.EXCLUSION_ACTION, middleware = guard)(manage)
    application.view(timesforge.slack.view.EXCLUSION_CALLBACK, middleware = guard)(exclude)
    application.action(timesforge.slack.view.RECREATION_ACTION, middleware = guard)(offer)
    application.view(timesforge.slack.view.RECREATION_CALLBACK, middleware = guard)(grant)
    application.action(timesforge.slack.view.IMPORT_ACTION, middleware = guard)(inquire)
    application.view(timesforge.slack.view.IMPORT_CALLBACK, middleware = guard)(reassign)
    application.action(timesforge.slack.view.HISTORY_ACTION, middleware = guard)(retrace)

    return recover

def detach(
    function: collections.abc.Callable[[], None]
) -> None:

    """Runs a function in a daemon thread, so that a listener returns at once and the app stops without waiting for it.

    Args:
        function: The function.
    """

    threading.Thread(target = function, daemon = True).start()
