"""Configuration read from environment variables and an optional .env file."""

import collections.abc
import dataclasses
import os
import pathlib
import re
import typing

import dotenv
import platformdirs

import timesforge.product

type Language = typing.Literal['en', 'ja']
type FieldRequired = typing.Literal['slack_bot_token', 'slack_app_token', 'slack_user_token', 'timesforge_owner_id', 'timesforge_channel_id_welcome']

_PATTERN_SLACK_USER_ID = re.compile(r'[UW][A-Z0-9]{2,}')
_PATTERN_SLACK_CHANNEL_ID = re.compile(r'C[A-Z0-9]{2,}')

class ConfigurationError(Exception):

    """Raised when the environment does not describe a usable configuration."""

@dataclasses.dataclass(frozen = True, kw_only = True, slots = True)
class Settings:

    """Validated settings for one deployment.

    Credentials that only some commands need are empty strings when unset.
    Commands call `require` before using them, so that every missing variable
    is reported at once.

    Attributes:
        slack_bot_token: Slack bot token (xoxb-...).
        slack_app_token: Slack app-level token (xapp-...) for Socket Mode.
        slack_user_token: Slack user token (xoxp-...) of an admin, which creates the times channels where only admins may create channels.
        timesforge_owner_id: Slack user ID of the owner of the app, the one user who administers it.
        timesforge_channel_id_welcome: Slack channel ID of the channel that new members join, such as #welcome, whose joining welcomes them.
        timesforge_data_directory: Local directory for the data.
        timesforge_language_display: Language for users whose Slack locale is unknown.
    """

    slack_bot_token: str
    slack_app_token: str
    slack_user_token: str
    timesforge_owner_id: str
    timesforge_channel_id_welcome: str
    timesforge_data_directory: pathlib.Path
    timesforge_language_display: Language

    def require(
        self,
        *fields: FieldRequired
    ) -> None:

        """Checks that settings needed by the caller are present.

        Args:
            *fields: Names of the settings that the caller needs.

        Raises:
            ConfigurationError: One or more of the settings are unset.
                                The message lists every missing environment variable.
        """

        missing = [field.upper() for field in fields if not getattr(self, field)]

        if missing: raise ConfigurationError(f'Missing required environment variables: {', '.join(missing)}')

def load(
    environment: collections.abc.Mapping[str, str] | None = None
) -> Settings:

    """Validates environment variables and builds settings from them.

    Error messages name the offending variable but never repeat its value,
    because the value may be a credential.

    Args:
        environment: Environment variables to build the settings from.
                     When None, the process environment is used, layered over
                     a .env file in the current directory if there is one.

    Returns:
        The validated settings.

    Raises:
        ConfigurationError: A variable has an invalid value.
    """

    if environment is None: environment = _read()

    slack_bot_token = _parse('SLACK_BOT_TOKEN', environment, category = 'environ')
    slack_app_token = _parse('SLACK_APP_TOKEN', environment, category = 'environ')
    slack_user_token = _parse('SLACK_USER_TOKEN', environment, category = 'environ')

    if slack_bot_token and not slack_bot_token.startswith('xoxb-'): raise ConfigurationError('SLACK_BOT_TOKEN must be a bot token starting with xoxb-')
    if slack_app_token and not slack_app_token.startswith('xapp-'): raise ConfigurationError('SLACK_APP_TOKEN must be an app-level token starting with xapp-')
    if slack_user_token and not slack_user_token.startswith('xoxp-'): raise ConfigurationError('SLACK_USER_TOKEN must be a user token starting with xoxp-')

    return Settings(
        slack_bot_token = slack_bot_token,
        slack_app_token = slack_app_token,
        slack_user_token = slack_user_token,
        timesforge_owner_id = _parse('TIMESFORGE_OWNER_ID', environment, category = 'user'),
        timesforge_channel_id_welcome = _parse('TIMESFORGE_CHANNEL_ID_WELCOME', environment, category = 'channel'),
        timesforge_data_directory = _parse('TIMESFORGE_DATA_DIRECTORY', environment, category = 'directory'),
        timesforge_language_display = _parse('TIMESFORGE_LANGUAGE_DISPLAY', environment, category = 'language')
    )

def _read() -> dict[str, str]:

    values = {key: value for key, value in dotenv.dotenv_values('.env').items() if value is not None}

    return {**values, **os.environ}

@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['environ']) -> str: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['user']) -> str: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['channel']) -> str: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['directory']) -> pathlib.Path: ...
@typing.overload
def _parse(name: str, environment: collections.abc.Mapping[str, str], *, category: typing.Literal['language']) -> Language: ...

def _parse(
    name: str,
    environment: collections.abc.Mapping[str, str],
    *,
    category: typing.Literal['environ', 'user', 'channel', 'directory', 'language']
) -> str | pathlib.Path | Language:

    value = environment.get(name, '').strip()

    match category:

        case 'environ':

            return value

        case 'user':

            if value and not _PATTERN_SLACK_USER_ID.fullmatch(value): raise ConfigurationError(f'{name} must be one Slack user ID')

            return value

        case 'channel':

            if value and not _PATTERN_SLACK_CHANNEL_ID.fullmatch(value): raise ConfigurationError(f'{name} must be one Slack channel ID')

            return value

        case 'directory':

            if not value: return platformdirs.user_data_path(timesforge.product.NAME, appauthor = False)

            return pathlib.Path(value).expanduser().resolve()

        case 'language':

            match value.lower():

                case 'en' | '': return 'en'
                case 'ja': return 'ja'
                case _: raise ConfigurationError(f'{name} must be "en" or "ja"')
