import datetime

import pytest

import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 25, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

REFUSALS = [('UXXX1', 'holder'), ('UXXX2', 'grant'), ('UXXX3', 'excluded'), ('UXXX4', 'right')]

def register(
    database: timesforge.storage.Database,
    channel_id: str,
    holder_id: str
) -> timesforge.times.registry.RegistryIO:

    store = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    store.save('TXXX', channel)

    return store

def test_recreation_grant_creation(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)

    store = timesforge.times.recreation.RecreationIO(database)

    grant = store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)

    assert grant == timesforge.times.recreation.Grant(grant_id = grant.grant_id, user_id = 'UXXX1', status = 'unused', owner_id = 'UXXX0', granting = CHANGE)
    assert store.find('TXXX', 'UXXX1') == [grant]
    assert store.find('TYYY', 'UXXX1') == []
    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') is None

@pytest.mark.parametrize(('user_id', 'expected'), REFUSALS)
def test_recreation_grant_refusal(
    database: timesforge.storage.Database,
    user_id: str,
    expected: str
) -> None:

    register(database, 'CXXX1', 'UXXX1')
    register(database, 'CXXX2', 'UXXX2').delete('TXXX', 'CXXX2', CREATION)
    register(database, 'CXXX3', 'UXXX3').delete('TXXX', 'CXXX3', CREATION)
    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX3', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION))
    store = timesforge.times.recreation.RecreationIO(database)
    store.grant('TXXX', 'UXXX2', owner_id = 'UXXX0', now = CHANGE)

    with pytest.raises(timesforge.times.recreation.GrantInvalidError) as exception: store.grant('TXXX', user_id, owner_id = 'UXXX0', now = CHANGE)

    assert exception.value.reason == expected

def test_recreation_workspace_scan(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)
    register(database, 'CXXX2', 'UXXX2').delete('TXXX', 'CXXX2', CREATION)

    store = timesforge.times.recreation.RecreationIO(database)

    grant = store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)
    store.grant('TXXX', 'UXXX2', owner_id = 'UXXX0', now = CHANGE); store.revoke('TXXX', 'UXXX2', owner_id = 'UXXX0', now = CHANGE)

    assert store.scan('TXXX') == [grant]
    assert store.scan('TYYY') == []

def test_recreation_grant_consumption(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)
    store = timesforge.times.recreation.RecreationIO(database)
    grant = store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    assert store.consume('TXXX', 'UXXX1', 'CXXX2', CHANGE)
    assert not store.consume('TXXX', 'UXXX1', 'CXXX3', CHANGE)
    assert store.find('TXXX', 'UXXX1') == [timesforge.times.recreation.Grant(grant_id = grant.grant_id, user_id = 'UXXX1', status = 'consumed', owner_id = 'UXXX0', granting = CREATION, consumption = CHANGE, channel_id = 'CXXX2')]
    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'used'

def test_recreation_grant_revocation(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)
    store = timesforge.times.recreation.RecreationIO(database)
    store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    assert store.revoke('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)
    assert not store.revoke('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)
    assert not store.consume('TXXX', 'UXXX1', 'CXXX2', CHANGE)
    assert [(grant.status, grant.revocation) for grant in store.find('TXXX', 'UXXX1')] == [('revoked', CHANGE)]
    assert timesforge.times.policy.decide(database.connect(), 'TXXX', 'UXXX1') == 'used'

    store.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)

    assert [grant.status for grant in store.find('TXXX', 'UXXX1')] == ['revoked', 'unused']
