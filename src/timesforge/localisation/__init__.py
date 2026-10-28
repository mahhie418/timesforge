"""Messages of the Slack app in English and Japanese."""

import functools
import importlib.resources
import json

import timesforge.configuration

def choose(
    locale: str | None,
    default: timesforge.configuration.Language
) -> timesforge.configuration.Language:

    """Chooses the language of a Slack user.

    Args:
        locale: Slack locale of the user, such as ja-JP, or None when unknown.
        default: Language for a locale that has no messages.

    Returns:
        The language.
    """

    if locale is None: return default
    if locale.startswith('ja'): return 'ja'
    if locale.startswith('en'): return 'en'

    return default

def translate(
    key: str,
    language: timesforge.configuration.Language,
    **values: str
) -> str:

    """Gives a message in a language.

    Args:
        key: Key of the message, such as home.times.
        language: The language.
        **values: Values for the placeholders in the message, such as channel.

    Returns:
        The message.
    """

    return _messages(language)[key].format(**values)

@functools.cache
def _messages(
    language: timesforge.configuration.Language
) -> dict[str, str]:

    return json.loads(importlib.resources.files('timesforge.localisation').joinpath(f'{language}.json').read_text(encoding = 'utf-8'))
