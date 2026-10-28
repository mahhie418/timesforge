import os
import pathlib

import platformdirs
import pytest

import timesforge.configuration
import timesforge.product

PREFIXES = ('TIMESFORGE_', 'SLACK_')

ENVIRONMENT_VALID = {
    'SLACK_BOT_TOKEN': 'xoxb-xxx',
    'SLACK_APP_TOKEN': 'xapp-xxx',
    'SLACK_USER_TOKEN': 'xoxp-xxx',
    'TIMESFORGE_OWNER_ID': ' UXXX ',
    'TIMESFORGE_LANGUAGE_DISPLAY': 'JA'
}

ENVIRONMENT_INVALID = [
    ('SLACK_BOT_TOKEN', 'xapp-xxx', 'SLACK_BOT_TOKEN'),
    ('SLACK_APP_TOKEN', 'xoxb-xxx', 'SLACK_APP_TOKEN'),
    ('SLACK_USER_TOKEN', 'xoxb-xxx', 'SLACK_USER_TOKEN'),
    ('TIMESFORGE_OWNER_ID', 'UXXX,WXXX', 'TIMESFORGE_OWNER_ID'),
    ('TIMESFORGE_LANGUAGE_DISPLAY', 'xxx', 'TIMESFORGE_LANGUAGE_DISPLAY')
]

@pytest.fixture
def isolated(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:

    monkeypatch.chdir(tmp_path)

    for name in [name for name in os.environ if name.startswith(PREFIXES)]: monkeypatch.delenv(name)

    return tmp_path

def test_configuration_values_default() -> None:

    settings = timesforge.configuration.load({})

    assert not settings.slack_bot_token
    assert not settings.slack_app_token
    assert not settings.slack_user_token
    assert not settings.timesforge_owner_id
    assert settings.timesforge_data_directory == platformdirs.user_data_path(timesforge.product.NAME, appauthor = False)
    assert settings.timesforge_language_display == 'en'

def test_configuration_values_parse() -> None:

    settings = timesforge.configuration.load(ENVIRONMENT_VALID)

    assert settings.slack_bot_token == ENVIRONMENT_VALID['SLACK_BOT_TOKEN']
    assert settings.slack_app_token == ENVIRONMENT_VALID['SLACK_APP_TOKEN']
    assert settings.slack_user_token == ENVIRONMENT_VALID['SLACK_USER_TOKEN']
    assert settings.timesforge_owner_id == 'UXXX'
    assert settings.timesforge_language_display == 'ja'

@pytest.mark.parametrize(('name', 'value', 'expected'), ENVIRONMENT_INVALID)
def test_configuration_values_invalid(
    name: str,
    value: str,
    expected: str
) -> None:

    with pytest.raises(timesforge.configuration.ConfigurationError, match = expected): timesforge.configuration.load({name: value})

def test_configuration_values_secure() -> None:

    with pytest.raises(timesforge.configuration.ConfigurationError) as exception: timesforge.configuration.load({'SLACK_BOT_TOKEN': 'xapp-xxx'})

    assert 'xapp-xxx' not in str(exception.value)

def test_configuration_values_present() -> None:

    settings = timesforge.configuration.load(ENVIRONMENT_VALID)
    settings.require('slack_bot_token', 'slack_app_token', 'slack_user_token', 'timesforge_owner_id')

def test_configuration_values_missing() -> None:

    settings = timesforge.configuration.load({})
    expected = r': SLACK_BOT_TOKEN, SLACK_APP_TOKEN$'

    with pytest.raises(timesforge.configuration.ConfigurationError, match = expected): settings.require('slack_bot_token', 'slack_app_token')

def test_configuration_directory_home() -> None:

    settings = timesforge.configuration.load({'TIMESFORGE_DATA_DIRECTORY': '~/xxx'})
    expected = pathlib.Path('~/xxx').expanduser().resolve()

    assert settings.timesforge_data_directory == expected

def test_configuration_directory_relative(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.chdir(tmp_path)

    settings = timesforge.configuration.load({'TIMESFORGE_DATA_DIRECTORY': 'xxx'})
    expected = pathlib.Path(os.path.join(tmp_path, 'xxx')).resolve()

    assert settings.timesforge_data_directory == expected

def test_configuration_dotenv_reading(
    isolated: pathlib.Path
) -> None:

    file = pathlib.Path(os.path.join(isolated, '.env'))
    file.write_text('TIMESFORGE_LANGUAGE_DISPLAY=ja\n', encoding = 'utf-8')

    settings = timesforge.configuration.load()

    assert settings.timesforge_language_display == 'ja'

def test_configuration_dotenv_override(
    isolated: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    file = pathlib.Path(os.path.join(isolated, '.env'))
    file.write_text('TIMESFORGE_LANGUAGE_DISPLAY=xxx\n', encoding = 'utf-8')

    monkeypatch.setenv('TIMESFORGE_LANGUAGE_DISPLAY', 'ja')
    settings = timesforge.configuration.load()

    assert settings.timesforge_language_display == 'ja'

@pytest.mark.usefixtures('isolated')
def test_configuration_dotenv_missing(
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', '~/xxx')
    settings = timesforge.configuration.load()
    expected = pathlib.Path('~/xxx').expanduser().resolve()

    assert settings.timesforge_data_directory == expected
