import datetime
import typing

import pytest
import slack_bolt
import slack_sdk

import timesforge.configuration
import timesforge.slack.handler
import timesforge.slack.permission
import timesforge.slack.view
import timesforge.storage
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 28, 15, 0, tzinfo = datetime.UTC)

TABS_OPENED = [('home', 1), ('messages', 0)]
VIEWERS_HOME = [('UXXX1', 'owner'), ('UXXX2', 'member')]

@pytest.fixture
def application(
    slack: slack_sdk.web.WebClient,
    database: timesforge.storage.Database
) -> slack_bolt.App:

    application = slack_bolt.App(client = slack, process_before_response = True)
    timesforge.slack.handler.register(application, timesforge.configuration.load({'TIMESFORGE_OWNER_ID': 'UXXX1'}), database)

    return application

def home(
    application: slack_bolt.App,
    user: str,
    tab: str
) -> slack_bolt.BoltResponse:

    return application.dispatch(slack_bolt.BoltRequest(body = {'type': 'event_callback', 'team_id': 'TXXX', 'event': {'type': 'app_home_opened', 'user': user, 'channel': 'DXXX', 'tab': tab}}, mode = 'socket_mode'))

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
    assert calls(workspace, 'views.publish') == [{'user_id': user, 'view': timesforge.slack.view.home(refusal = 'holder', role = role)}]

@pytest.mark.parametrize(('tab', 'count'), TABS_OPENED)
def test_handler_home_tab(
    application: slack_bolt.App,
    workspace: dict[str, typing.Any],
    tab: str,
    count: int
) -> None:

    home(application, 'UXXX1', tab)

    assert calls(workspace, 'views.publish') == [{'user_id': 'UXXX1', 'view': timesforge.slack.view.home(refusal = None, role = 'owner')}] * count
