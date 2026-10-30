# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import importlib.resources
import json

import pytest

import timesforge.configuration
import timesforge.localisation

LOCALES_CHOSEN = [
    ('ja-JP', 'en', 'ja'),
    ('en-GB', 'ja', 'en'),
    ('fr-FR', 'ja', 'ja'),
    (None, 'en', 'en')
]

def test_localisation_key_consistency() -> None:

    keys = [set(json.loads(importlib.resources.files('timesforge.localisation').joinpath(f'{language}.json').read_text(encoding = 'utf-8'))) for language in ('en', 'ja')]

    assert keys[0] == keys[1]

@pytest.mark.parametrize(('locale', 'default', 'expected'), LOCALES_CHOSEN)
def test_localisation_locale_choice(
    locale: str | None,
    default: timesforge.configuration.Language,
    expected: timesforge.configuration.Language
) -> None:

    assert timesforge.localisation.choose(locale, default) == expected

def test_localisation_message_translation() -> None:

    assert [timesforge.localisation.translate('home.times', language) for language in ('en', 'ja')] == ['times channel', 'times チャンネル']

def test_localisation_value_insertion() -> None:

    assert timesforge.localisation.translate('home.times.approved', 'ja', channel = '#times_xxx') == '#times_xxx が承認されました。'
