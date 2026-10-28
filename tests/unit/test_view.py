import pytest

import timesforge.configuration
import timesforge.slack.permission
import timesforge.slack.view
import timesforge.times.policy

STATES_HOME = [
    (None, 'en', ['*times channel*\nYou can create one.']),
    ('holder', 'ja', ['*times チャンネル*\n作成済みです。']),
    ('used', 'en', ['*times channel*\nYours was deleted.']),
    ('excluded', 'en', ['*times channel*\nYou cannot create one.'])
]

ROLES_MESSAGE = [
    ('owner', ['You are the owner.']),
    ('member', [])
]

@pytest.mark.parametrize(('refusal', 'language', 'texts'), STATES_HOME)
def test_view_home_status(
    refusal: timesforge.times.policy.Refusal | None,
    language: timesforge.configuration.Language,
    texts: list[str]
) -> None:

    view = timesforge.slack.view.home(refusal = refusal, role = 'member', language = language)

    assert view['type'] == 'home'
    assert [field['text'] for block in view['blocks'] if 'fields' in block for field in block['fields']] == texts

@pytest.mark.parametrize(('role', 'texts'), ROLES_MESSAGE)
def test_view_home_role(
    role: timesforge.slack.permission.Role,
    texts: list[str]
) -> None:

    view = timesforge.slack.view.home(refusal = None, role = role, language = 'en')

    assert [element['text'] for block in view['blocks'] if block['type'] == 'context' for element in block['elements']] == texts
