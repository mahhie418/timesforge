import dataclasses
import datetime

import pytest

import timesforge.configuration
import timesforge.slack.permission
import timesforge.slack.view
import timesforge.times.exclusion
import timesforge.times.history
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

CREATION = datetime.datetime(2026, 10, 28, 15, 0, tzinfo = datetime.UTC)

PROMPT = 'A times channel is your own public channel, `#times_(First Name)`, where you post whatever you like. Enter your first name, and TimesForge creates the channel and invites the members of the workspace. Each member can normally create one times channel, once.'

REQUEST_RESERVED = timesforge.times.request.Request(request_id = 1, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'reserved', grant_id = None, creation = CREATION)
REQUEST_PENDING = timesforge.times.request.Request(request_id = 1, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'pending_name_resolution', grant_id = None, creation = CREATION)
REQUEST_CREATING = timesforge.times.request.Request(request_id = 1, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'reconciling', grant_id = None, error = 'xxx', creation = CREATION)
REQUEST_FAILED = timesforge.times.request.Request(request_id = 1, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'failed', grant_id = None, error = 'restricted_action', creation = CREATION)
REQUEST_COMPLETED = timesforge.times.request.Request(request_id = 1, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'completed', grant_id = None, channel_id = 'CXXX1', creation = CREATION)

STATES_HOME = [
    (None, None, 'en', [PROMPT, '*times channel*\nYou can create one.'], [timesforge.slack.view.CREATION_ACTION]),
    ('holder', None, 'ja', ['*times チャンネル*\n作成済みです。'], []),
    ('used', None, 'en', ['*times channel*\nYours was deleted. Creating another needs permission from the owner.'], []),
    ('excluded', None, 'en', ['*times channel*\nYou cannot create one.'], []),
    (None, REQUEST_RESERVED, 'en', ['*times channel*\n#times_xxx is approved.'], []),
    (None, REQUEST_PENDING, 'en', ['*times channel*\n#times_xxx is taken. The owner will choose another name.'], []),
    ('holder', REQUEST_CREATING, 'en', ['*times channel*\n#times_xxx is being created.'], []),
    (None, REQUEST_FAILED, 'en', [PROMPT, '*times channel*\n#times_xxx could not be created (restricted_action). You can try again.'], [timesforge.slack.view.CREATION_ACTION]),
    ('holder', REQUEST_COMPLETED, 'en', ['*times channel*\nYou have one.'], [])
]

REQUESTS_DECIDED = [
    (REQUEST_RESERVED, 'Approved. #times_xxx is to be created.'),
    (REQUEST_PENDING, '#times_xxx is taken, so the owner will choose another name for you.')
]

REQUESTS_REPORTED = [
    (REQUEST_COMPLETED, 'Created <#CXXX1>.'),
    (REQUEST_FAILED, '#times_xxx could not be created (restricted_action).'),
    (REQUEST_PENDING, '#times_xxx is taken, so the owner will choose another name for you.'),
    (REQUEST_CREATING, '#times_xxx is being created. The App Home shows when it is ready.')
]

CHANNELS_HELD = [
    timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'deleted', creation = CREATION, deletion = CREATION),
    timesforge.times.registry.Channel(channel_id = 'CXXX2', holder_id = 'UXXX1', first_name = 'Yyy', channel_name = 'times_yyy', source = 'imported', status = 'archived', creation = CREATION, archival = CREATION),
    timesforge.times.registry.Channel(channel_id = 'CXXX3', holder_id = 'UXXX1', first_name = 'Zzz', channel_name = 'times_zzz', creation = CREATION)
]

EXCLUSIONS_LISTED = [
    timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'xxx', owner_id = 'UXXX1', creation = CREATION),
    timesforge.times.exclusion.Exclusion(user_id = 'UXXX3', reason = 'yyy', owner_id = 'UXXX1', creation = CREATION)
]

GRANTS_LISTED = [timesforge.times.recreation.Grant(grant_id = 1, user_id = 'UXXX4', status = 'unused', owner_id = 'UXXX1', granting = CREATION)]

ENTRIES_TRACED = [
    timesforge.times.history.Entry(action = 'rename', target_id = 'UXXX1', channel_id = 'CXXX1', details = {'channel_name': 'xxx'}, creation = CREATION),
    timesforge.times.history.Entry(action = 'exclude', actor_id = 'UXXX1', target_id = 'UXXX2', details = {'reason': 'xxx'}, creation = CREATION)
]

ROLES_MESSAGE = [
    ('owner', ['You are the owner.']),
    ('member', [])
]

@pytest.mark.parametrize(('refusal', 'reservation', 'language', 'texts', 'actions'), STATES_HOME)
def test_view_home_status(
    refusal: timesforge.times.policy.Refusal | None,
    reservation: timesforge.times.request.Request | None,
    language: timesforge.configuration.Language,
    texts: list[str],
    actions: list[str]
) -> None:

    view = timesforge.slack.view.home(refusal = refusal, eligible = True, request = reservation, channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = language)

    assert view['type'] == 'home'
    assert [block['text']['text'] for block in view['blocks'] if block['type'] == 'section'] == texts
    assert [block['accessory']['action_id'] for block in view['blocks'] if 'accessory' in block] == actions

def test_view_home_guest() -> None:

    view = timesforge.slack.view.home(refusal = None, eligible = False, request = None, channels = [], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'en')

    assert [(block['text']['text'], 'accessory' in block) for block in view['blocks']] == [('*times channel*\nOnly members can create one.', False)]

def test_view_home_channels() -> None:

    view = timesforge.slack.view.home(refusal = 'holder', eligible = True, request = None, channels = CHANNELS_HELD, exclusions = [], grants = [], conflicts = [], role = 'member', language = 'en')

    assert [block['text']['text'] for block in view['blocks'] if block['type'] == 'section'][1:] == ['*Your times channels*\n#times_xxx (deleted <!date^1793199600^{date_short}|2026-10-28>)\n<#CXXX2> (archived <!date^1793199600^{date_short}|2026-10-28>)\n<#CXXX3> (created <!date^1793199600^{date_short}|2026-10-28>)']

def test_view_home_recreation() -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'deleted', creation = CREATION, deletion = CREATION)
    view = timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [channel], exclusions = [], grants = [], conflicts = [], role = 'member', language = 'en')

    assert [block['text']['text'] for block in view['blocks']][:2] == [PROMPT, '*times channel*\nThe owner let you create one more.']
    assert [block['accessory']['action_id'] for block in view['blocks'] if 'accessory' in block] == [timesforge.slack.view.CREATION_ACTION]

def test_view_home_owner() -> None:

    view = timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = EXCLUSIONS_LISTED, grants = GRANTS_LISTED, conflicts = [], role = 'owner', language = 'en')
    member = timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = EXCLUSIONS_LISTED, grants = GRANTS_LISTED, conflicts = [], role = 'member', language = 'en')

    assert [block['text']['text'] for block in view['blocks'] if block['type'] == 'header'] == ['Owner actions']
    assert [(block['text']['text'], block.get('accessory', {}).get('action_id')) for block in view['blocks'] if block['type'] == 'section'][2:] == [('*Name conflicts*\nNone', None), ('*Excluded members*\n<@UXXX2>, <@UXXX3>', timesforge.slack.view.EXCLUSION_ACTION), ('*Recreation grants*\n<@UXXX4>', timesforge.slack.view.RECREATION_ACTION), ('*Imported channels*\nCheck who holds the times channels created before TimesForge, and correct them.', timesforge.slack.view.IMPORT_ACTION), ('*History*\nThe latest changes to the times channels and to who may create them.', timesforge.slack.view.HISTORY_ACTION)]
    assert [block['type'] for block in member['blocks']] == ['section', 'section']

def test_view_home_conflicts() -> None:

    view = timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = [], grants = [], conflicts = [REQUEST_PENDING, dataclasses.replace(REQUEST_PENDING, request_id = 2, user_id = 'UXXX2')], role = 'owner', language = 'en')

    assert [(block['text']['text'], block['accessory']['value']) for block in view['blocks'] if block.get('accessory', {}).get('action_id') == timesforge.slack.view.RESOLUTION_ACTION] == [('*Name conflicts*\n<@UXXX1> asked for #times_xxx, which is taken.', '1'), ('*Name conflicts*\n<@UXXX2> asked for #times_xxx, which is taken.', '2')]

def test_view_resolution_modal() -> None:

    view = timesforge.slack.view.resolve(request = REQUEST_PENDING, language = 'en')

    assert (view['callback_id'], view['private_metadata']) == (timesforge.slack.view.RESOLUTION_CALLBACK, '1')
    assert view['blocks'][0]['text']['text'].startswith('<@UXXX1> asked for #times_xxx, which is taken.')
    assert [block['block_id'] for block in view['blocks'] if block['type'] == 'input'] == [timesforge.slack.view.NAME_INPUT]

def test_view_exclusion_modal() -> None:

    view = timesforge.slack.view.exclude(exclusions = EXCLUSIONS_LISTED, language = 'en')
    empty = timesforge.slack.view.exclude(exclusions = [], language = 'en')

    assert view['callback_id'] == timesforge.slack.view.EXCLUSION_CALLBACK
    assert view['blocks'][0]['text']['text'] == '<@UXXX2> (xxx)\n<@UXXX3> (yyy)'
    assert empty['blocks'][0]['text']['text'] == 'No member is excluded.'
    assert [block['block_id'] for block in view['blocks'] if block['type'] == 'input'] == [timesforge.slack.view.MEMBER_INPUT, timesforge.slack.view.CHOICE_INPUT, timesforge.slack.view.REASON_INPUT]

def test_view_recreation_modal() -> None:

    view = timesforge.slack.view.grant(grants = GRANTS_LISTED, language = 'en')

    assert view['callback_id'] == timesforge.slack.view.RECREATION_CALLBACK
    assert view['blocks'][0]['text']['text'].endswith('\n<@UXXX4>')
    assert [block['block_id'] for block in view['blocks'] if block['type'] == 'input'] == [timesforge.slack.view.MEMBER_INPUT, timesforge.slack.view.CHOICE_INPUT]

def test_view_import_modal() -> None:

    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', source = 'imported', creation = CREATION)
    view = timesforge.slack.view.review(channels = [channel], language = 'en')
    empty = timesforge.slack.view.review(channels = [], language = 'en')

    assert view['callback_id'] == timesforge.slack.view.IMPORT_CALLBACK
    assert view['blocks'][0]['text']['text'] == '<#CXXX1> (<@UXXX1>)'
    assert [option['value'] for option in view['blocks'][1]['element']['options']] == ['CXXX1']
    assert [block['text']['text'] for block in empty['blocks']] == ['No times channel was imported.']

def test_view_history_modal() -> None:

    view = timesforge.slack.view.trace(entries = ENTRIES_TRACED, language = 'en')
    empty = timesforge.slack.view.trace(entries = [], language = 'en')

    assert [block['text']['text'] for block in view['blocks']] == ['<!date^1793199600^{date_short} {time}|2026-10-28 15:00 UTC> <#CXXX1> was renamed to #xxx.', '<!date^1793199600^{date_short} {time}|2026-10-28 15:00 UTC> <@UXXX1> excluded <@UXXX2> from creating times channels.']
    assert [block['text']['text'] for block in empty['blocks']] == ['Nothing has changed yet.']

def test_view_welcome_message() -> None:

    text, blocks = timesforge.slack.view.welcome(workspace = 'xxx', team_id = 'TXXX', app_id = 'AXXX', language = 'en')

    assert text.startswith('Welcome to xxx!\nYou can create your own public channel, `#times_(First Name)`.')
    assert [block['text']['text'] for block in blocks] == [f'*Welcome to xxx!*\n{text.split('\n', 1)[1]}', '<slack://app?team=TXXX&id=AXXX&tab=home|Create your times>']

def test_view_ready_message() -> None:

    text, blocks = timesforge.slack.view.ready(channel_id = 'CXXX1', language = 'en')

    assert text == 'Your times channel is ready!\nYou can find your channel here:\n<#CXXX1>'
    assert [block['text']['text'] for block in blocks] == ['*Your times channel is ready!*\nYou can find your channel here:\n<#CXXX1>']

@pytest.mark.parametrize(('role', 'texts'), ROLES_MESSAGE)
def test_view_home_role(
    role: timesforge.slack.permission.Role,
    texts: list[str]
) -> None:

    view = timesforge.slack.view.home(refusal = None, eligible = True, request = None, channels = [], exclusions = [], grants = [], conflicts = [], role = role, language = 'en')

    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == texts

def test_view_creation_modal() -> None:

    view = timesforge.slack.view.collect(language = 'ja')

    assert view['callback_id'] == timesforge.slack.view.CREATION_CALLBACK
    assert [(block['block_id'], block['element']['max_length']) for block in view['blocks'] if block['type'] == 'input'] == [(timesforge.slack.view.NAME_INPUT, 74)]

@pytest.mark.parametrize(('reservation', 'text'), REQUESTS_DECIDED)
def test_view_approval_modal(
    reservation: timesforge.times.request.Request,
    text: str
) -> None:

    view = timesforge.slack.view.approve(request = reservation, language = 'en')

    assert [block['text']['text'] for block in view['blocks']] == [text]

@pytest.mark.parametrize(('reservation', 'text'), REQUESTS_REPORTED)
def test_view_creation_report(
    reservation: timesforge.times.request.Request,
    text: str
) -> None:

    view = timesforge.slack.view.report(request = reservation, language = 'en')

    assert [block['text']['text'] for block in view['blocks']] == [text]
