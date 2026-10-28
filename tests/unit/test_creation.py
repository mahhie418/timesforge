import datetime
import typing

import pytest
import slack_sdk

import timesforge.slack.creation
import timesforge.slack.invitation
import timesforge.storage
import timesforge.times.history
import timesforge.times.invitation
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

CREATION = datetime.datetime(2026, 10, 26, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(minutes = 1)

FAILURES_RECOVERED = [['lost'], ['dropped'], [500]]
STATUSES_RESUMED = ['reserved', 'reconciling', 'created', 'inviting']

@pytest.fixture
def requests(
    database: timesforge.storage.Database
) -> timesforge.times.request.RequestIO:

    return timesforge.times.request.RequestIO(database)

@pytest.fixture
def creator(
    database: timesforge.storage.Database,
    writer: slack_sdk.web.WebClient,
    slack: slack_sdk.web.WebClient,
    requests: timesforge.times.request.RequestIO
) -> timesforge.slack.creation.Creator:

    inviter = timesforge.slack.invitation.Inviter(slack, writer, timesforge.times.invitation.InvitationIO(database), 'TXXX')

    return timesforge.slack.creation.Creator(writer, slack, requests, 'TXXX', inviter)

def reserve(
    requests: timesforge.times.request.RequestIO,
    first_name: str = 'Yyy'
) -> int:

    return requests.reserve('TXXX', 'UXXX1', first_name, CREATION).request_id

def names(
    workspace: dict[str, typing.Any]
) -> list[str]:

    return [channel['name'] for channel in workspace['channels']]

def leave(
    requests: timesforge.times.request.RequestIO,
    writer: slack_sdk.web.WebClient,
    status: timesforge.times.request.Status
) -> int:

    request_id = reserve(requests)

    if status == 'reserved': return request_id

    requests.start('TXXX', request_id, CREATION)

    if status == 'reconciling': requests.lose('TXXX', request_id, error = 'xxx', now = CREATION); return request_id

    channel = writer.conversations_create(name = 'times_yyy', is_private = False).get('channel', {})
    registration = timesforge.times.registry.Channel(channel_id = channel['id'], holder_id = 'UXXX1', first_name = 'Yyy', channel_name = 'times_yyy', creation = CREATION)

    requests.finish('TXXX', request_id, registration, creator_id = 'UXXX0', now = CREATION)

    if status == 'inviting': requests.advance('TXXX', request_id, CREATION)

    return request_id

def test_creation_channel_success(
    database: timesforge.storage.Database,
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    request = creator.create(reserve(requests), CHANGE)

    assert request is not None
    assert (request.status, request.channel_id) == ('completed', 'CXXX3')
    assert workspace['members']['CXXX3'] == ['UXXX0', 'UXXXB', 'UXXX1', 'UXXX2', 'UXXX3', 'UXXX4']
    assert workspace['channels'][-1] == {'id': 'CXXX3', 'name': 'times_yyy', 'is_private': False, 'is_archived': False, 'created': workspace['clock'], 'creator': 'UXXX0'}
    assert timesforge.times.registry.RegistryIO(database).load('TXXX', 'CXXX3') == timesforge.times.registry.Channel(channel_id = 'CXXX3', holder_id = 'UXXX1', first_name = 'Yyy', channel_name = 'times_yyy', creation = CREATION)
    assert timesforge.times.history.HistoryIO(database).load('TXXX', 1) == [timesforge.times.history.Entry(action = 'create', actor_id = 'UXXX1', target_id = 'UXXX1', channel_id = 'CXXX3', details = {'creator': 'UXXX0'}, creation = CHANGE)]

def test_creation_name_conflict(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    request = creator.create(reserve(requests, 'Xxx'), CHANGE)

    assert request is not None
    assert request.status == 'pending_name_resolution'
    assert names(workspace) == ['times_xxx', 'xxx']

def test_creation_slack_refusal(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    workspace['failures'] = ['restricted_action']

    request = creator.create(reserve(requests), CHANGE)

    assert request is not None
    assert (request.status, request.error) == ('failed', 'restricted_action')
    assert requests.reserve('TXXX', 'UXXX1', 'Yyy', CHANGE).request_id != request.request_id

@pytest.mark.parametrize('failures', FAILURES_RECOVERED)
def test_creation_result_recovery(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator,
    failures: list[str | int]
) -> None:

    workspace['failures'] = list(failures)

    request = creator.create(reserve(requests), CHANGE)

    assert request is not None
    assert (request.status, request.channel_id, request.error) == ('completed', 'CXXX3', None)
    assert names(workspace) == ['times_xxx', 'xxx', 'times_yyy']

def test_creation_result_unknown(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    workspace['failures'] = ['dropped', 'dropped']

    request = creator.create(request_id := reserve(requests), CHANGE)

    assert request is not None
    assert (request.status, request.error) == ('reconciling', 'xxx')
    assert creator.create(request_id, CHANGE) == request
    assert names(workspace) == ['times_xxx', 'xxx']

    request = creator.reconcile(request_id, CHANGE)

    assert request is not None
    assert request.status == 'completed'
    assert names(workspace) == ['times_xxx', 'xxx', 'times_yyy']

def test_creation_request_busy(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    requests.start('TXXX', request_id := reserve(requests), CREATION)

    request = creator.create(request_id, CHANGE)

    assert request is not None
    assert request.status == 'creating'
    assert creator.reconcile(request_id, CHANGE) == request
    assert creator.create(request_id + 1, CHANGE) is None
    assert names(workspace) == ['times_xxx', 'xxx']

@pytest.mark.parametrize('status', STATUSES_RESUMED)
def test_creation_request_resumption(
    workspace: dict[str, typing.Any],
    writer: slack_sdk.web.WebClient,
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator,
    status: timesforge.times.request.Status
) -> None:

    request = creator.resume(leave(requests, writer, status), CHANGE)

    assert request is not None
    assert (request.status, request.channel_id) == ('completed', 'CXXX3')
    assert names(workspace) == ['times_xxx', 'xxx', 'times_yyy']
    assert workspace['members']['CXXX3'] == ['UXXX0', 'UXXXB', 'UXXX1', 'UXXX2', 'UXXX3', 'UXXX4']

def test_creation_resumption_busy(
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    requests.start('TXXX', request_id := reserve(requests), CREATION)

    request = creator.resume(request_id, CHANGE)

    assert request is not None
    assert request.status == 'creating'
    assert creator.resume(request_id + 1, CHANGE) is None
    assert names(workspace) == ['times_xxx', 'xxx']

def test_creation_grant_consumption(
    database: timesforge.storage.Database,
    workspace: dict[str, typing.Any],
    requests: timesforge.times.request.RequestIO,
    creator: timesforge.slack.creation.Creator
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    registry.save('TXXX', channel)
    registry.delete('TXXX', 'CXXX1', CREATION)

    grants = timesforge.times.recreation.RecreationIO(database)
    grant = grants.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    workspace['failures'] = ['restricted_action']
    creator.create(reserve(requests), CHANGE)

    assert [item.status for item in grants.find('TXXX', 'UXXX1')] == ['unused']

    creator.create(reserve(requests), CHANGE)

    assert [(item.grant_id, item.status, item.channel_id) for item in grants.find('TXXX', 'UXXX1')] == [(grant.grant_id, 'consumed', 'CXXX3')]
