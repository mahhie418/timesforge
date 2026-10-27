import datetime

import timesforge.storage
import timesforge.times.exclusion

CREATION = datetime.datetime(2026, 10, 25, 15, 0, tzinfo = datetime.UTC)

def create(
    user_id: str,
    creation: datetime.datetime = CREATION
) -> timesforge.times.exclusion.Exclusion:

    return timesforge.times.exclusion.Exclusion(user_id = user_id, reason = 'xxx', owner_id = 'UXXX0', creation = creation)

def test_exclusion_member_addition(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.exclusion.ExclusionIO(database)
    exclusion = create('UXXX1')

    assert store.add('TXXX', exclusion)
    assert not store.add('TXXX', create('UXXX1', CREATION + datetime.timedelta(days = 1)))
    assert store.load('TXXX', 'UXXX1') == exclusion
    assert store.load('TXXX', 'UXXX2') is None
    assert store.load('TYYY', 'UXXX1') is None

def test_exclusion_member_removal(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.exclusion.ExclusionIO(database)
    store.add('TXXX', create('UXXX1'))
    store.add('TYYY', create('UXXX1'))

    assert store.remove('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)
    assert not store.remove('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)
    assert store.load('TXXX', 'UXXX1') is None
    assert store.load('TYYY', 'UXXX1') is not None

def test_exclusion_workspace_member(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.exclusion.ExclusionIO(database)
    exclusions = [create('UXXX2'), create('UXXX1', CREATION + datetime.timedelta(days = 1))]

    for exclusion in exclusions: store.add('TXXX', exclusion)

    store.add('TYYY', create('UXXX3'))

    assert store.find('TXXX') == exclusions
    assert store.find('TZZZ') == []
