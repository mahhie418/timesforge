import collections.abc
import datetime
import typing
import unittest.mock

import pytest
import slack_bolt
import slack_sdk
import slack_sdk.errors

import timesforge.configuration
import timesforge.slack.handler
import timesforge.slack.permission
import timesforge.slack.reconciliation
import timesforge.slack.view
import timesforge.storage
import timesforge.times.policy
import timesforge.times.registry

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
    slack: slack_sdk.web.WebClient,
    database: timesforge.storage.Database
) -> tuple[slack_bolt.App, collections.abc.Callable[[str, datetime.datetime], None]]:

    application = slack_bolt.App(client = slack, process_before_response = True)

    return application, timesforge.slack.handler.register(application, timesforge.configuration.load({'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_LANGUAGE_DISPLAY': 'ja'}), database)

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
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = 'holder', role = role, language = 'ja')}]

def test_handler_home_locale(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any]
) -> None:

    next(entry for entry in workspace['users'] if entry['id'] == 'UXXX1')['locale'] = 'en-GB'

    assert home(application, 'UXXX1', 'home').status == 200
    assert calls(workspace, 'users.info') == [{'user': 'UXXX1', 'include_locale': True}]
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, role = 'owner', language = 'en')}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, role = 'owner', language = 'ja')}] * count

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
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = refusal, role = 'member', language = 'ja')} for user, refusal in views]

def test_handler_channel_recovery(
    workspace: dict[str, typing.Any],
    recover: collections.abc.Callable[[str, datetime.datetime], None],
    registry: timesforge.times.registry.RegistryIO
) -> None:

    recover('TXXX', CREATION)

    assert [channel.status for holder in ('UXXX1', 'UXXX2', 'UXXX3') for channel in registry.find('TXXX', holder)] == ['active', 'archived', 'deleted']
    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX2', 'view': timesforge.slack.view.home(refusal = 'holder', role = 'member', language = 'ja')}, {'user_id': 'UXXX3', 'view': timesforge.slack.view.home(refusal = 'used', role = 'member', language = 'ja')}]

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
