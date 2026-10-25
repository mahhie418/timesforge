import datetime
import json
import os
import pathlib
import typing

import pytest
import slack_sdk

import timesforge.slack.existing
import timesforge.storage
import timesforge.times.history
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 26, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

MAPPINGS_INVALID = ['xxx', '[]', '{"xxx": "UXXX1"}', '{"CXXX1": "xxx"}', '{"CXXX1": 1}']

CHANNELS_EXTRA = [
    {'id': 'CXXX3', 'name': 'times_yyy', 'is_private': False, 'is_archived': True, 'created': 1793026800, 'creator': 'UXXX0'},
    {'id': 'CXXX4', 'name': 'times_zzz', 'is_private': True, 'is_archived': False, 'created': 1793026800, 'creator': 'UXXX0'},
    {'id': 'CXXX5', 'name': 'times_xxx_yyy', 'is_private': False, 'is_archived': False, 'created': 1793026800, 'creator': 'UXXX0'}
]

@pytest.fixture
def registry(
    database: timesforge.storage.Database,
    workspace: dict[str, typing.Any]
) -> timesforge.times.registry.RegistryIO:

    workspace['channels'] += CHANNELS_EXTRA

    return timesforge.times.registry.RegistryIO(database)

def test_existing_mapping_reading(
    tmp_path: pathlib.Path
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, 'xxx.json'))
    file.write_text(json.dumps({'CXXX1': 'UXXX1', 'CXXX2': 'UXXX2'}), encoding = 'utf-8')

    assert timesforge.slack.existing.read(file) == {'CXXX1': 'UXXX1', 'CXXX2': 'UXXX2'}

@pytest.mark.parametrize('text', MAPPINGS_INVALID)
def test_existing_mapping_invalid(
    tmp_path: pathlib.Path,
    text: str
) -> None:

    file = pathlib.Path(os.path.join(tmp_path, 'xxx.json'))
    file.write_text(text, encoding = 'utf-8')

    with pytest.raises(timesforge.slack.existing.MappingInvalidError): timesforge.slack.existing.read(file)

def test_existing_channel_findings(
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    mapping = {'CXXX1': 'UXXX1', 'CXXX2': 'UXXX2', 'CXXX3': 'UXXX3', 'CXXX4': 'UXXX4', 'CXXX5': 'UXXX5', 'CXXX6': 'UXXX6', 'CXXX7': 'UXXX8', 'CXXX8': 'UXXX8'}
    findings = timesforge.slack.existing.check(slack, registry, 'TXXX', mapping, CHANGE)

    expected = [
        ('CXXX1', 'import', None),
        ('CXXX2', 'error', 'name'),
        ('CXXX3', 'import', None),
        ('CXXX4', 'error', 'private'),
        ('CXXX5', 'error', 'name'),
        ('CXXX6', 'error', 'channel_not_found'),
        ('CXXX7', 'error', 'duplicate'),
        ('CXXX8', 'error', 'duplicate')
    ]

    assert [(finding.channel_id, finding.verdict, finding.reason) for finding in findings] == expected
    assert findings[0].channel == timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'xxx', channel_name = 'times_xxx', source = 'imported', creation = CREATION)
    assert findings[2].channel == timesforge.times.registry.Channel(channel_id = 'CXXX3', holder_id = 'UXXX3', first_name = 'yyy', channel_name = 'times_yyy', source = 'imported', status = 'archived', creation = CREATION, archival = CHANGE)

def test_existing_holder_refusal(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    channels: list[dict[str, typing.Any]] = workspace['channels']
    channels.append({'id': 'CXXX6', 'name': 'times_www', 'is_private': False, 'is_archived': False, 'created': 1793026800, 'creator': 'UXXX0'})

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX6', holder_id = 'UXXX2', first_name = 'www', channel_name = 'times_www', creation = CREATION)

    registry.save('TXXX', channel)

    mapping = {'CXXX1': 'UXXX2', 'CXXX3': 'UXXX5', 'CXXX6': 'UXXX1', 'CXXX4': 'UXXX9'}
    findings = timesforge.slack.existing.check(slack, registry, 'TXXX', mapping, CHANGE)

    assert [(finding.verdict, finding.reason) for finding in findings] == [('error', 'held'), ('error', 'holder'), ('error', 'registered'), ('error', 'private')]

def test_existing_channel_registration(
    database: timesforge.storage.Database,
    slack: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO
) -> None:

    mapping = {'CXXX1': 'UXXX1', 'CXXX3': 'UXXX3'}
    findings = timesforge.slack.existing.check(slack, registry, 'TXXX', mapping, CHANGE)

    assert timesforge.slack.existing.register(database, 'TXXX', findings, CHANGE) == 2
    assert [channel.source for channel in registry.find('TXXX', 'UXXX1') + registry.find('TXXX', 'UXXX3')] == ['imported', 'imported']
    assert [(entry.action, entry.target_id, entry.channel_id) for entry in timesforge.times.history.HistoryIO(database).load('TXXX', 10)] == [('import', 'UXXX3', 'CXXX3'), ('import', 'UXXX1', 'CXXX1')]

    findings = timesforge.slack.existing.check(slack, registry, 'TXXX', mapping, CHANGE)

    assert [(finding.verdict, finding.reason) for finding in findings] == [('skip', 'registered'), ('skip', 'registered')]
    assert timesforge.slack.existing.register(database, 'TXXX', findings, CHANGE) == 0
