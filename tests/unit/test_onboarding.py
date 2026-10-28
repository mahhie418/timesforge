import dataclasses
import datetime

import timesforge.storage
import timesforge.times.onboarding

CREATION = datetime.datetime(2026, 10, 25, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(minutes = 1)

PENDING = timesforge.times.onboarding.Message(user_id = 'UXXX1', channel_id = 'CXXX1', event_id = 'EvXXX1', status = 'pending', creation = CREATION)

def claim(
    store: timesforge.times.onboarding.OnboardingIO,
    workspace_id: str = 'TXXX',
    event_id: str = 'EvXXX1'
) -> bool:

    return store.claim(workspace_id, 'UXXX1', channel_id = 'CXXX1', event_id = event_id, now = CREATION)

def test_onboarding_welcome_claim(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database)

    assert claim(store)
    assert not claim(store)
    assert not claim(store, event_id = 'EvXXX2')
    assert claim(store, workspace_id = 'TYYY')
    assert store.load('TXXX', 'UXXX1') == PENDING
    assert store.load('TXXX', 'UXXX2') is None

def test_onboarding_message_delivery(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database); claim(store)

    assert not store.succeed('TXXX', 'UXXX1', conversation_id = 'DXXX', message_ts = '1.2', now = CHANGE)
    assert store.send('TXXX', 'UXXX1', CHANGE)
    assert not store.send('TXXX', 'UXXX1', CHANGE)
    assert store.succeed('TXXX', 'UXXX1', conversation_id = 'DXXX', message_ts = '1.2', now = CHANGE)
    assert not store.send('TXXX', 'UXXX1', CHANGE)
    assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'sent', conversation_id = 'DXXX', message_ts = '1.2', delivery = CHANGE)

def test_onboarding_message_failure(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database); claim(store)
    store.send('TXXX', 'UXXX1', CHANGE)

    assert store.fail('TXXX', 'UXXX1', error = 'xxx', now = CHANGE)
    assert not store.fail('TXXX', 'UXXX1', error = 'xxx', now = CHANGE)
    assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'failed', error = 'xxx')
    assert store.send('TXXX', 'UXXX1', CHANGE)
    assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'sending')

def test_onboarding_message_loss(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database); claim(store)
    store.send('TXXX', 'UXXX1', CHANGE)

    assert store.lose('TXXX', 'UXXX1', error = 'xxx', now = CHANGE)
    assert not store.send('TXXX', 'UXXX1', CHANGE)
    assert not store.fail('TXXX', 'UXXX1', error = 'xxx', now = CHANGE)
    assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'unknown', error = 'xxx')
    assert store.succeed('TXXX', 'UXXX1', conversation_id = 'DXXX', message_ts = '1.2', now = CHANGE)

def test_onboarding_message_update(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database); claim(store)
    store.send('TXXX', 'UXXX1', CHANGE)

    assert not store.update('TXXX', 'UXXX1', CHANGE)
    assert store.succeed('TXXX', 'UXXX1', conversation_id = 'DXXX', message_ts = '1.2', now = CHANGE)
    assert store.update('TXXX', 'UXXX1', CHANGE)
    assert store.update('TXXX', 'UXXX1', CHANGE)
    assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'updated', conversation_id = 'DXXX', message_ts = '1.2', delivery = CHANGE)

def test_onboarding_workspace_scan(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database)

    claim(store)
    store.claim('TXXX', 'UXXX2', channel_id = 'CXXX1', event_id = 'EvXXX2', now = CHANGE); store.send('TXXX', 'UXXX2', CHANGE)
    claim(store, workspace_id = 'TYYY')

    assert store.scan('TXXX', ['pending']) == [PENDING]
    assert [message.user_id for message in store.scan('TXXX', ['pending', 'sending'])] == ['UXXX1', 'UXXX2']

def test_onboarding_restart_persistence(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.onboarding.OnboardingIO(database); claim(store)
    store.send('TXXX', 'UXXX1', CHANGE)

    database.close()

    restart = timesforge.storage.Database(database.path)

    try:

        store = timesforge.times.onboarding.OnboardingIO(restart)

        assert not claim(store, event_id = 'EvXXX2')
        assert store.load('TXXX', 'UXXX1') == dataclasses.replace(PENDING, status = 'sending')

    finally:

        restart.close()
