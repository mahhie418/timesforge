import datetime

import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)

def register(
    database: timesforge.storage.Database,
    channel_id: str,
    holder_id: str
) -> timesforge.times.registry.RegistryIO:

    store = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    store.save('TXXX', channel)

    return store

def test_policy_right_first(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1')

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX2') is None
    assert timesforge.times.policy.decide(database.connect(), 'TYYY', 'UXXX1') is None

def test_policy_holder_active(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1')

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'holder'

def test_policy_holder_archived(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').archive('TXXX', 'CXXX1', CREATION)

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'holder'

def test_policy_right_used(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'used'

def test_policy_member_excluded(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.exclusion.ExclusionIO(database)
    channels = [timesforge.times.exclusion.Exclusion(user_id = 'UXXX1', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION), timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION)]

    for channel in channels: store.add('TXXX', channel)

    register(database, 'CXXX1', 'UXXX2')

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'excluded'
    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX2') == 'excluded'
    assert timesforge.times.policy.decide(database.connect(), 'TYYY', 'UXXX1') is None

    store.remove('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') is None

def test_policy_grant_unused(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)

    store = timesforge.times.recreation.RecreationIO(database)

    store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') is None

    store.consume('TXXX', 'UXXX1', 'CXXX2', CREATION)

    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'used'
