import datetime
import typing

import pytest
import slack_sdk

import timesforge.slack.reconciliation
import timesforge.storage
import timesforge.times.history
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 26, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

@pytest.fixture
def registry(
    database: timesforge.storage.Database
) -> timesforge.times.registry.RegistryIO:

    store = timesforge.times.registry.RegistryIO(database)

    for channel_id, holder_id, channel_name in [('CXXX1', 'UXXX1', 'times_xxx'), ('CXXX2', 'UXXX2', 'times_yyy'), ('CXXX3', 'UXXX3', 'times_zzz')]: store.save('TXXX', timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = channel_name, creation = CREATION))

    return store

def test_reconciliation_channel_state(
    database: timesforge.storage.Database,
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    assert timesforge.slack.reconciliation.reconcile(slack, registry, 'TXXX', CHANGE) == ['CXXX2', 'CXXX3']
    assert [(channel.channel_id, channel.channel_name, channel.status) for channel in registry.find('TXXX', 'UXXX1') + registry.find('TXXX', 'UXXX2') + registry.find('TXXX', 'UXXX3')] == [('CXXX1', 'times_xxx', 'active'), ('CXXX2', 'xxx', 'archived'), ('CXXX3', 'times_zzz', 'deleted')]
    assert timesforge.times.history.HistoryIO(database).load('TXXX', 10)[::-1] == [timesforge.times.history.Entry(action = 'archive', target_id = 'UXXX2', channel_id = 'CXXX2', creation = CHANGE), timesforge.times.history.Entry(action = 'rename', target_id = 'UXXX2', channel_id = 'CXXX2', details = {'channel_name': 'xxx'}, creation = CHANGE), timesforge.times.history.Entry(action = 'delete', target_id = 'UXXX3', channel_id = 'CXXX3', creation = CHANGE)]
    assert timesforge.slack.reconciliation.reconcile(slack, registry, 'TXXX', CHANGE) == []

def test_reconciliation_channel_restoration(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    timesforge.slack.reconciliation.reconcile(slack, registry, 'TXXX', CREATION)
    workspace['channels'][1] |= {'name': 'times_yyy', 'is_archived': False}

    assert timesforge.slack.reconciliation.reconcile(slack, registry, 'TXXX', CHANGE) == ['CXXX2']
    assert [(channel.channel_name, channel.status) for channel in registry.find('TXXX', 'UXXX2')] == [('times_yyy', 'active')]

def test_reconciliation_channel_selection(
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    assert timesforge.slack.reconciliation.reconcile(slack, registry, 'TXXX', CHANGE, ['CXXX1', 'CXXX3']) == ['CXXX3']
    assert [channel.status for channel in registry.find('TXXX', 'UXXX2')] == ['active']
