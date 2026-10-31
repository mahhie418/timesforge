# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import pytest

import timesforge.times.naming

NAMES_VALID = [
    ('xxx', 'times_xxx'),
    ('XXX', 'times_xxx'),
    ('Xxx-Xxx', 'times_xxx-xxx'),
    (' xxx\u3000', 'times_xxx'),
    ('x' * 74, f'times_{'x' * 74}')
]

NAMES_INVALID = [
    ('', 'empty'),
    (' \t\u3000', 'empty'),
    ('漢字', 'characters'),
    ('xxx xxx', 'characters'),
    ('-xxx', 'characters'),
    ('xxx-', 'characters'),
    ('xxx--xxx', 'characters'),
    ('xxx_xxx', 'characters'),
    ('xxx1', 'characters'),
    ('\uff58\uff58\uff58', 'characters'),
    ('\u212axxx', 'characters'),
    ('x' * 75, 'length')
]

@pytest.mark.parametrize(('first_name', 'expected'), NAMES_VALID)
def test_naming_names_valid(
    first_name: str,
    expected: str
) -> None:

    assert timesforge.times.naming.sanitise(first_name) == expected

@pytest.mark.parametrize(('first_name', 'expected'), NAMES_INVALID)
def test_naming_names_invalid(
    first_name: str,
    expected: str
) -> None:

    with pytest.raises(timesforge.times.naming.NameInvalidError) as exception: timesforge.times.naming.sanitise(first_name)

    assert exception.value.reason == expected
