import collections.abc
import dataclasses
import datetime
import json
import threading
import typing
import unittest.mock

import pytest
import slack_bolt
import slack_sdk
import slack_sdk.errors

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.handler
import timesforge.slack.permission
import timesforge.slack.reconciliation
import timesforge.slack.view
import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.history
import timesforge.times.naming
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

CREATION = datetime.datetime(2026, 10, 28, 15, 0, tzinfo = datetime.UTC)

TABS_OPENED = [('home', 1), ('messages', 0)]
VIEWERS_HOME = [('UXXX1', 'owner'), ('UXXX2', 'member')]

CHANNELS_REGISTERED = [('CXXX1', 'UXXX1', 'times_xxx'), ('CXXX2', 'UXXX2', 'times_yyy'), ('CXXX3', 'UXXX3', 'times_zzz')]

EVENTS_CHANNEL = [
    ({'type': 'channel_archive', 'channel': 'CXXX2', 'user': 'UXXX1'}, 'UXXX2', [('archived', 'xxx')], [('UXXX2', 'holder')]),
    ({'type': 'channel_rename', 'channel': {'id': 'CXXX2', 'name': 'xxx', 'created': 1793026800}}, 'UXXX2', [('archived', 'xxx')], [('UXXX2', 'holder')]),
    ({'type': 'channel_deleted', 'channel': 'CXXX3'}, 'UXXX3', [('deleted', 'times_zzz')], [('UXXX3', 'used')]),
    ({'type': 'channel_unarchive', 'channel': 'CXXX1', 'user': 'UXXX1'}, 'UXXX1', [('active', 'times_xxx')], [])
]

NAMES_INVALID = [(' ', 'empty'), ('漢字', 'characters'), ('X' * 75, 'length')]

EXCLUSIONS_REFUSED = [
    ('UXXX3', 'exclude', ' ', timesforge.slack.view.REASON_INPUT, 'exclusion.error.reason'),
    ('UXXX2', 'exclude', 'yyy', timesforge.slack.view.MEMBER_INPUT, 'exclusion.error.exclude'),
    ('UXXX3', 'include', '', timesforge.slack.view.MEMBER_INPUT, 'exclusion.error.include')
]

RESOLUTIONS_REFUSED = [('Xxx', 'resolution.error.taken'), ('漢字', 'creation.error.characters')]

IMPORTS_REFUSED = [('UXXX5', 'review.error.ineligible'), ('UXXX2', 'review.error.held'), ('UXXX1', 'review.error.unchanged')]

GRANTS_REFUSED = [
    ('UXXX1', 'grant', 'recreation.error.holder'),
    ('UXXX2', 'grant', 'recreation.error.grant'),
    ('UXXX3', 'grant', 'recreation.error.excluded'),
    ('UXXX4', 'grant', 'recreation.error.right'),
    ('UXXX4', 'revoke', 'recreation.error.revoke')
]

@pytest.fixture
def application(
    registration: tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]
) -> slack_bolt.App:

    return registration[0]

@pytest.fixture
def recover(
    registration: tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]
) -> collections.abc.Callable[[str, datetime.datetime], None]:

    return registration[1]

@pytest.fixture
def registration(
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient,
    writer: slack_sdk.web.WebClient,
    database: timesforge.storage.Database
) -> tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]:

    def detach(
        function: collections.abc.Callable[[], None]
    ) -> None:

        function()

    application = slack_bolt.App(client = slack, process_before_response = True)
    monkeypatch.setattr(timesforge.slack.handler, 'detach', detach)

    return application, timesforge.slack.handler.register(application, timesforge.configuration.load({'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_LANGUAGE_DISPLAY': 'ja'}), database, writer)

@pytest.fixture
def registry(
    database: timesforge.storage.Database
) -> timesforge.times.registry.RegistryIO:

    store = timesforge.times.registry.RegistryIO(database)

    for channel_id, holder_id, channel_name in CHANNELS_REGISTERED: store.save('TXXX', timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = channel_name, creation = CREATION))

    return store

def home(
    application: slack_bolt.App,
    user: str,
    tab: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'event_callback', 'team_id': 'TXXX', 'event': {'type': 'app_home_opened', 'user': user, 'channel': 'DXXX', 'tab': tab}}, mode = 'socket_mode'))

def change(
    application: slack_bolt.App,
    event: dict[str, typing.Any]
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'event_callback', 'team_id': 'TXXX', 'event': event}, mode = 'socket_mode'))

def press(
    application: slack_bolt.App,
    user: str,
    action: str,
    *,
    value: str | None = None
) -> slack_bolt.BoltResponse:

    button = {'type': 'button', 'action_id': action}

    if value is not None: button['value'] = value

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'trigger_id': 'xxx', 'actions': [button]}, mode = 'socket_mode'))

def submit(
    application: slack_bolt.App,
    user: str,
    view: dict[str, typing.Any]
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'view_submission', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'view': {'id': 'VXXX', 'type': 'modal', 'state': {'values': {}}} | view}, mode = 'socket_mode'))

def named(
    first_name: str
) -> dict[str, typing.Any]:

    return {'callback_id': timesforge.slack.view.CREATION_CALLBACK, 'state': {'values': {timesforge.slack.view.NAME_INPUT: {timesforge.slack.view.NAME_INPUT: {'type': 'plain_text_input', 'value': first_name}}}}}

def resolved(
    request_id: int,
    name: str
) -> dict[str, typing.Any]:

    return {'callback_id': timesforge.slack.view.RESOLUTION_CALLBACK, 'private_metadata': str(request_id), 'state': {'values': {timesforge.slack.view.NAME_INPUT: {timesforge.slack.view.NAME_INPUT: {'type': 'plain_text_input', 'value': name}}}}}

def excluded(
    user: str,
    choice: str,
    reason: str | None
) -> dict[str, typing.Any]:

    return {'callback_id': timesforge.slack.view.EXCLUSION_CALLBACK, 'state': {'values': {timesforge.slack.view.MEMBER_INPUT: {timesforge.slack.view.MEMBER_INPUT: {'type': 'users_select', 'selected_user': user}}, timesforge.slack.view.CHOICE_INPUT: {timesforge.slack.view.CHOICE_INPUT: {'type': 'radio_buttons', 'selected_option': {'value': choice}}}, timesforge.slack.view.REASON_INPUT: {timesforge.slack.view.REASON_INPUT: {'type': 'plain_text_input', 'value': reason}}}}}

def reassigned(
    channel_id: str,
    user: str
) -> dict[str, typing.Any]:

    return {'callback_id': timesforge.slack.view.IMPORT_CALLBACK, 'state': {'values': {timesforge.slack.view.CHANNEL_INPUT: {timesforge.slack.view.CHANNEL_INPUT: {'type': 'static_select', 'selected_option': {'value': channel_id}}}, timesforge.slack.view.MEMBER_INPUT: {timesforge.slack.view.MEMBER_INPUT: {'type': 'users_select', 'selected_user': user}}}}}

def granted(
    user: str,
    choice: str
) -> dict[str, typing.Any]:

    return {'callback_id': timesforge.slack.view.RECREATION_CALLBACK, 'state': {'values': {timesforge.slack.view.MEMBER_INPUT: {timesforge.slack.view.MEMBER_INPUT: {'type': 'users_select', 'selected_user': user}}, timesforge.slack.view.CHOICE_INPUT: {timesforge.slack.view.CHOICE_INPUT: {'type': 'radio_buttons', 'selected_option': {'value': choice}}}}}}

def calls(
    workspace: dict[str, typing.Any],
    method: str
) -> list[dict[str, typing.Any]]:

    return [arguments for name, arguments in workspace['calls'] if name == method]

@pytest.mark.parametrize(('user', 'role'), VIEWERS_HOME)
def test_handler_home_publication(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database,
    user: str,
    role: timesforge.slack.permission.Role
) -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = user, first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    timesforge.times.registry.RegistryIO(database).save('TXXX', channel)

    assert home(application, user, 'home').status == 200
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = None, channels = [channel], exclusions = [], grants = [], conflicts = [], role = role, language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = [], grants = [], conflicts = [], role = 'owner', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = [], grants = [], conflicts = [], role = 'owner', language = 'ja')}] * count

@pytest.mark.parametrize(('event', 'holder', 'states', 'views'), EVENTS_CHANNEL)
def test_handler_channel_change(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    registry: timesforge.times.registry.RegistryIO,
    event: dict[str, typing.Any],
    holder: str,
    states: list[tuple[timesforge.times.registry.Status, str]],
    views: list[tuple[str, timesforge.times.policy.Refusal]]
) -> None:

    assert change(application, event).status == 200
    assert [(channel.status, channel.channel_name) for channel in registry.find('TXXX', holder)] == states
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = refusal, eligible = True, request = None, channels = registry.find('TXXX', user), exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')} for user, refusal in views]

def test_handler_channel_recovery(
    workspace: dict[str, typing.Any],
    recover: collections.abc.Callable[[str, datetime.datetime], None],
    registry: timesforge.times.registry.RegistryIO
) -> None:

    recover('TXXX', CREATION)

    assert [channel.status for holder in ('UXXX1', 'UXXX2', 'UXXX3') for channel in registry.find('TXXX', holder)] == ['active', 'archived', 'deleted']
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = None, channels = registry.find('TXXX', 'UXXX2'), exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}, {'user_id': 'UXXX3', 'view': timesforge.slack.view.home(refusal = 'used', eligible = True, request = None, channels = registry.find('TXXX', 'UXXX3'), exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}]

@pytest.mark.usefixtures('registry')
def test_handler_recovery_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    workspace: dict[str, typing.Any],
    recover: collections.abc.Callable[[str, datetime.datetime], None]
) -> None:

    monkeypatch.setattr(timesforge.slack.reconciliation, 'reconcile', unittest.mock.Mock(side_effect = slack_sdk.errors.SlackApiError('xxx', 'xxx')))

    recover('TXXX', CREATION)

    assert 'Times channels were not reconciled' in caplog.text
    assert calls(workspace, 'views.publish') == []

def test_handler_request_recovery(
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database,
    recover: collections.abc.Callable[[str, datetime.datetime], None]
) -> None:

    requests = timesforge.times.request.RequestIO(database)

    requests.start('TXXX', requests.reserve('TXXX', 'UXXX2', 'Yyy', CREATION).request_id, CREATION)
    requests.reserve('TXXX', 'UXXX3', 'Zzz', CREATION)

    recover('TXXX', CREATION)

    assert [(request.user_id, request.status, request.channel_id) for user in ('UXXX2', 'UXXX3') for request in requests.find('TXXX', user)] == [('UXXX2', 'completed', 'CXXX3'), ('UXXX3', 'completed', 'CXXX4')]
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX2', 'UXXX3']

def test_handler_creation_modal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    assert press(application, 'UXXX2', timesforge.slack.view.CREATION_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.collect(language = 'ja')}]

def test_handler_channel_creation(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    response = submit(application, 'UXXX2', named(' Yyy '))
    requests = timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2')
    reservation = dataclasses.replace(requests[0], status = 'reserved', channel_id = None)

    assert json.loads(response.body) == {'response_action': 'update', 'view': timesforge.slack.view.approve(request = reservation, language = 'ja')}
    assert [(request.first_name, request.channel_name, request.status, request.channel_id) for request in requests] == [('Yyy', 'times_yyy', 'completed', 'CXXX3')]
    assert workspace['members']['CXXX3'] == ['UXXX0', 'UXXXB', 'UXXX1', 'UXXX2', 'UXXX3', 'UXXX4']
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': timesforge.slack.view.report(request = requests[0], language = 'ja')}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = reservation, channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}, {'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = requests[0], channels = timesforge.times.registry.RegistryIO(database).find('TXXX', 'UXXX2'), exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}]

def test_handler_creation_failure(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    workspace['failures'] = ['restricted_action']

    submit(application, 'UXXX2', named('Yyy'))
    requests = timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2')

    assert [(request.status, request.error) for request in requests] == [('failed', 'restricted_action')]
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': timesforge.slack.view.report(request = requests[0], language = 'ja')}]
    assert calls(workspace, 'views.publish')[-1] == {'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = requests[0], channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}

def test_handler_modal_closure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    application: slack_bolt.App,
    slack: slack_sdk.web.WebClient,
    database: timesforge.storage.Database
) -> None:

    monkeypatch.setattr(slack, 'views_update', unittest.mock.Mock(side_effect = slack_sdk.errors.SlackApiError('xxx', 'xxx')))

    submit(application, 'UXXX2', named('Yyy'))

    assert 'Modal not updated' in caplog.text
    assert [request.status for request in timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2')] == ['completed']

@pytest.mark.parametrize(('first_name', 'reason'), NAMES_INVALID)
def test_handler_name_invalid(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database,
    first_name: str,
    reason: timesforge.times.naming.Reason
) -> None:

    response = submit(application, 'UXXX2', named(first_name))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate(f'creation.error.{reason}', 'ja')}}
    assert timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2') == []
    assert calls(workspace, 'views.publish') == []

def test_handler_creation_refusal(
    application: slack_bolt.App,
    database: timesforge.storage.Database
) -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX2', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    timesforge.times.registry.RegistryIO(database).save('TXXX', channel)

    response = submit(application, 'UXXX2', named('Yyy'))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('creation.refusal.holder', 'ja')}}
    assert timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2') == []

def test_handler_creation_pending(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    timesforge.times.registry.RegistryIO(database).save('TXXX', channel)

    response = submit(application, 'UXXX2', named('Xxx'))
    requests = timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX2')

    assert [request.status for request in requests] == ['pending_name_resolution']
    assert json.loads(response.body) == {'response_action': 'update', 'view': timesforge.slack.view.approve(request = requests[0], language = 'ja')}
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = requests[0], channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}]

def test_handler_guest_refusal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    response = submit(application, 'UXXX5', named('Yyy'))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('creation.refusal.ineligible', 'ja')}}
    assert timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX5') == []
    assert home(application, 'UXXX5', 'home').status == 200
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX5', 'view': timesforge.slack.view.home(refusal = None, eligible = False, request = None, channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')}]

def test_handler_conflict_resolution(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    registry.save('TXXX', channel)

    requests = timesforge.times.request.RequestIO(database)
    request = requests.reserve('TXXX', 'UXXX2', 'Xxx', CREATION)

    assert press(application, 'UXXX2', timesforge.slack.view.RESOLUTION_ACTION, value = str(request.request_id)).status == 200
    assert calls(workspace, 'views.open') == []
    assert press(application, 'UXXX1', timesforge.slack.view.RESOLUTION_ACTION, value = str(request.request_id)).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.resolve(request = request, language = 'ja')}]

    response = submit(application, 'UXXX1', resolved(request.request_id, 'Xxx-Yyy'))
    result = requests.load('TXXX', request.request_id)

    assert result is not None
    assert (result.user_id, result.channel_name, result.status, result.channel_id) == ('UXXX2', 'times_xxx-yyy', 'completed', 'CXXX3')
    assert json.loads(response.body) == {'response_action': 'update', 'view': timesforge.slack.view.approve(request = dataclasses.replace(result, status = 'reserved', channel_id = None), language = 'ja')}
    assert calls(workspace, 'views.update') == [{'view_id': 'VXXX', 'view': timesforge.slack.view.report(request = result, language = 'ja')}]
    assert [(item.channel_id, item.channel_name) for item in registry.find('TXXX', 'UXXX2')] == [('CXXX3', 'times_xxx-yyy')]
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1', 'UXXX2']

    response = submit(application, 'UXXX1', resolved(request.request_id, 'Zzz'))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('resolution.error.settled', 'ja')}}
    assert press(application, 'UXXX1', timesforge.slack.view.RESOLUTION_ACTION, value = str(request.request_id)).status == 200
    assert len(calls(workspace, 'views.open')) == 1

@pytest.mark.parametrize(('name', 'key'), RESOLUTIONS_REFUSED)
def test_handler_resolution_refusal(
    application: slack_bolt.App,
    database: timesforge.storage.Database,
    name: str,
    key: str
) -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    timesforge.times.registry.RegistryIO(database).save('TXXX', channel)

    requests = timesforge.times.request.RequestIO(database)
    request = requests.reserve('TXXX', 'UXXX2', 'Xxx', CREATION)

    response = submit(application, 'UXXX1', resolved(request.request_id, name))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate(key, 'ja')}}
    assert requests.load('TXXX', request.request_id) == request

def test_handler_exclusion_modal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    assert press(application, 'UXXX2', timesforge.slack.view.EXCLUSION_ACTION).status == 200
    assert calls(workspace, 'views.open') == []
    assert press(application, 'UXXX1', timesforge.slack.view.EXCLUSION_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.exclude(exclusions = [], language = 'ja')}]

def test_handler_member_exclusion(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    timesforge.times.registry.RegistryIO(database).save('TXXX', channel)

    requests = timesforge.times.request.RequestIO(database); requests.reserve('TXXX', 'UXXX2', 'Xxx', CREATION)

    store = timesforge.times.exclusion.ExclusionIO(database)

    assert submit(application, 'UXXX2', excluded('UXXX2', 'exclude', 'xxx')).status == 200
    assert store.find('TXXX') == []

    response = submit(application, 'UXXX1', excluded('UXXX2', 'exclude', ' xxx '))
    exclusion = store.load('TXXX', 'UXXX2')

    assert (response.status, response.body) == (200, '')
    assert exclusion is not None
    assert (exclusion.reason, exclusion.owner_id) == ('xxx', 'UXXX1')
    assert [(request.status, request.error) for request in requests.find('TXXX', 'UXXX2')] == [('failed', 'excluded')]
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1', 'UXXX2']
    assert calls(workspace, 'views.publish')[1]['view'] == timesforge.slack.view.home(refusal = 'excluded', eligible = True, request = requests.find('TXXX', 'UXXX2')[0], channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')

    submit(application, 'UXXX1', excluded('UXXX2', 'include', None))

    assert store.find('TXXX') == []
    assert [entry.action for entry in timesforge.times.history.HistoryIO(database).load('TXXX', 10)] == ['include', 'exclude']

@pytest.mark.parametrize(('user', 'choice', 'reason', 'block', 'key'), EXCLUSIONS_REFUSED)
def test_handler_exclusion_refusal(
    application: slack_bolt.App,
    database: timesforge.storage.Database,
    user: str,
    choice: str,
    reason: str,
    block: str,
    key: str
) -> None:

    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'xxx', owner_id = 'UXXX1', creation = CREATION))

    response = submit(application, 'UXXX1', excluded(user, choice, reason))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {block: timesforge.localisation.translate(key, 'ja')}}

def test_handler_recreation_modal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    assert press(application, 'UXXX2', timesforge.slack.view.RECREATION_ACTION).status == 200
    assert calls(workspace, 'views.open') == []
    assert press(application, 'UXXX1', timesforge.slack.view.RECREATION_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.grant(grants = [], language = 'ja')}]

def test_handler_recreation_grant(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX2', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    registry.save('TXXX', channel)
    registry.delete('TXXX', 'CXXX1', CREATION)

    store = timesforge.times.recreation.RecreationIO(database)

    assert submit(application, 'UXXX2', granted('UXXX2', 'grant')).status == 200
    assert store.scan('TXXX') == []

    response = submit(application, 'UXXX1', granted('UXXX2', 'grant'))
    grants = store.scan('TXXX')

    assert (response.status, response.body) == (200, '')
    assert [(grant.user_id, grant.status, grant.owner_id) for grant in grants] == [('UXXX2', 'unused', 'UXXX1')]
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1', 'UXXX2']
    assert calls(workspace, 'views.publish')[1]['view'] == timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = registry.find('TXXX', 'UXXX2'), exclusions = [], grants = [], conflicts = [], role = 'member', language = 'ja')

    submit(application, 'UXXX1', granted('UXXX2', 'revoke'))

    assert store.scan('TXXX') == []
    assert [grant.status for grant in store.find('TXXX', 'UXXX2')] == ['revoked']

@pytest.mark.parametrize(('user', 'choice', 'key'), GRANTS_REFUSED)
def test_handler_recreation_refusal(
    application: slack_bolt.App,
    database: timesforge.storage.Database,
    user: str,
    choice: str,
    key: str
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)

    for channel_id, holder_id in [('CXXX1', 'UXXX1'), ('CXXX2', 'UXXX2'), ('CXXX3', 'UXXX3')]: registry.save('TXXX', timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION))
    for channel_id in ('CXXX2', 'CXXX3'): registry.delete('TXXX', channel_id, CREATION)

    timesforge.times.recreation.RecreationIO(database).grant('TXXX', 'UXXX2', owner_id = 'UXXX1', now = CREATION)
    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX3', reason = 'xxx', owner_id = 'UXXX1', creation = CREATION))

    response = submit(application, 'UXXX1', granted(user, choice))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.MEMBER_INPUT: timesforge.localisation.translate(key, 'ja')}}

def test_handler_import_review(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    imported = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', source = 'imported', creation = CREATION)
    created = timesforge.times.registry.Channel(channel_id = 'CXXX2', holder_id = 'UXXX2', first_name = 'Yyy', channel_name = 'times_yyy', creation = CREATION)

    for channel in (imported, created): registry.save('TXXX', channel)

    assert press(application, 'UXXX2', timesforge.slack.view.IMPORT_ACTION).status == 200
    assert calls(workspace, 'views.open') == []
    assert press(application, 'UXXX1', timesforge.slack.view.IMPORT_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.review(channels = [imported], language = 'ja')}]

    response = submit(application, 'UXXX1', reassigned('CXXX1', 'UXXX3'))

    assert (response.status, response.body) == (200, '')
    assert [channel.channel_id for channel in registry.find('TXXX', 'UXXX3')] == ['CXXX1']
    assert [arguments['user_id'] for arguments in calls(workspace, 'views.publish')] == ['UXXX1', 'UXXX3']

@pytest.mark.parametrize(('user', 'key'), IMPORTS_REFUSED)
def test_handler_import_refusal(
    application: slack_bolt.App,
    database: timesforge.storage.Database,
    user: str,
    key: str
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    imported = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', source = 'imported', creation = CREATION)
    created = timesforge.times.registry.Channel(channel_id = 'CXXX2', holder_id = 'UXXX2', first_name = 'Yyy', channel_name = 'times_yyy', creation = CREATION)

    for channel in (imported, created): registry.save('TXXX', channel)

    response = submit(application, 'UXXX1', reassigned('CXXX1', user))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.MEMBER_INPUT: timesforge.localisation.translate(key, 'ja')}}
    assert [channel.holder_id for channel in registry.scan('TXXX')] == ['UXXX1', 'UXXX2']

def test_handler_history_modal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'xxx', owner_id = 'UXXX1', creation = CREATION))

    assert press(application, 'UXXX2', timesforge.slack.view.HISTORY_ACTION).status == 200
    assert calls(workspace, 'views.open') == []
    assert press(application, 'UXXX1', timesforge.slack.view.HISTORY_ACTION).status == 200
    assert calls(workspace, 'views.open') == [{'trigger_id': 'xxx', 'view': timesforge.slack.view.trace(entries = timesforge.times.history.HistoryIO(database).load('TXXX', timesforge.slack.handler.HISTORY_LIMIT), language = 'ja')}]

def test_handler_thread_detachment() -> None:

    threads: list[threading.Thread] = []
    started = threading.Event()

    def run() -> None:

        threads.append(threading.current_thread())
        started.set()

    timesforge.slack.handler.detach(run)

    assert started.wait(5)
    assert threads[0] is not threading.current_thread()
    assert threads[0].daemon
