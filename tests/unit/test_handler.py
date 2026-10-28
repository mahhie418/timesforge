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
import timesforge.times.naming
import timesforge.times.policy
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
    action: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'block_actions', 'team': {'id': 'TXXX'}, 'user': {'id': user}, 'trigger_id': 'xxx', 'actions': [{'type': 'button', 'action_id': action}]}, mode = 'socket_mode'))

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
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = None, channels = [channel], role = role, language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], role = 'owner', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], role = 'owner', language = 'ja')}] * count

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
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = refusal, eligible = True, request = None, channels = registry.find('TXXX', user), role = 'member', language = 'ja')} for user, refusal in views]

def test_handler_channel_recovery(
    workspace: dict[str, typing.Any],
    recover: collections.abc.Callable[[str, datetime.datetime], None],
    registry: timesforge.times.registry.RegistryIO
) -> None:

    recover('TXXX', CREATION)

    assert [channel.status for holder in ('UXXX1', 'UXXX2', 'UXXX3') for channel in registry.find('TXXX', holder)] == ['active', 'archived', 'deleted']
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = None, channels = registry.find('TXXX', 'UXXX2'), role = 'member', language = 'ja')}, {'user_id': 'UXXX3', 'view': timesforge.slack.view.home(refusal = 'used', eligible = True, request = None, channels = registry.find('TXXX', 'UXXX3'), role = 'member', language = 'ja')}]

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
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = reservation, channels = [], role = 'member', language = 'ja')}, {'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = 'holder', eligible = True, request = requests[0], channels = timesforge.times.registry.RegistryIO(database).find('TXXX', 'UXXX2'), role = 'member', language = 'ja')}]

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
    assert calls(workspace, 'views.publish')[-1] == {'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = requests[0], channels = [], role = 'member', language = 'ja')}

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
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = None, eligible = True, request = requests[0], channels = [], role = 'member', language = 'ja')}]

def test_handler_guest_refusal(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    database: timesforge.storage.Database
) -> None:

    response = submit(application, 'UXXX5', named('Yyy'))

    assert json.loads(response.body) == {'response_action': 'errors', 'errors': {timesforge.slack.view.NAME_INPUT: timesforge.localisation.translate('creation.refusal.ineligible', 'ja')}}
    assert timesforge.times.request.RequestIO(database).find('TXXX', 'UXXX5') == []
    assert home(application, 'UXXX5', 'home').status == 200
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX5', 'view': timesforge.slack.view.home(refusal = None, eligible = False, request = None, channels = [], role = 'member', language = 'ja')}]

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
