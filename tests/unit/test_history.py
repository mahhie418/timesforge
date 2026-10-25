import datetime

import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.history
import timesforge.times.recreation
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

def test_history_entry_recording(
    database: timesforge.storage.Database
) -> None:

    entries = [timesforge.times.history.Entry(action = 'rename', channel_id = 'CXXX1', details = {'channel_name': 'xxx'}, creation = CREATION), timesforge.times.history.Entry(action = 'exclude', actor_id = 'UXXX0', target_id = 'UXXX1', creation = CHANGE)]

    with database.begin() as connection:

        for entry in entries: timesforge.times.history.record(connection, 'TXXX', entry)

        timesforge.times.history.record(connection, 'TYYY', entries[0])

    store = timesforge.times.history.HistoryIO(database)

    assert store.load('TXXX', 10) == entries[::-1]
    assert store.load('TXXX', 1) == entries[1:]
    assert store.load('TZZZ', 10) == []

def test_history_administration_change(
    database: timesforge.storage.Database
) -> None:

    exclusions = timesforge.times.exclusion.ExclusionIO(database)
    exclusions.add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION))
    exclusions.add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX2', reason = 'yyy', owner_id = 'UXXX0', creation = CREATION))
    exclusions.remove('TXXX', 'UXXX2', owner_id = 'UXXX0', now = CHANGE)
    exclusions.remove('TXXX', 'UXXX2', owner_id = 'UXXX0', now = CHANGE)

    registry = timesforge.times.registry.RegistryIO(database)
    registry.save('TXXX', timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION))
    registry.delete('TXXX', 'CXXX1', CHANGE)

    grants = timesforge.times.recreation.RecreationIO(database)
    grant = grants.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)
    grants.revoke('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)
    grants.revoke('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)

    assert timesforge.times.history.HistoryIO(database).load('TXXX', 10)[::-1] == [
        timesforge.times.history.Entry(action = 'exclude', actor_id = 'UXXX0', target_id = 'UXXX2', details = {'reason': 'xxx'}, creation = CREATION),
        timesforge.times.history.Entry(action = 'include', actor_id = 'UXXX0', target_id = 'UXXX2', creation = CHANGE),
        timesforge.times.history.Entry(action = 'delete', target_id = 'UXXX1', channel_id = 'CXXX1', creation = CHANGE),
        timesforge.times.history.Entry(action = 'grant', actor_id = 'UXXX0', target_id = 'UXXX1', details = {'grant_id': str(grant.grant_id)}, creation = CHANGE),
        timesforge.times.history.Entry(action = 'revoke', actor_id = 'UXXX0', target_id = 'UXXX1', creation = CHANGE)
    ]

def test_history_lifecycle_change(
    database: timesforge.storage.Database
) -> None:

    registry = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    registry.save('TXXX', channel)

    for operation in (registry.archive, registry.archive, registry.unarchive): operation('TXXX', 'CXXX1', CHANGE, actor_id = 'UXXX2')
    for name in ('xxx', 'xxx'): registry.rename('TXXX', 'CXXX1', name, CHANGE)

    registry.delete('TXXX', 'CXXX2', CHANGE)

    assert timesforge.times.history.HistoryIO(database).load('TXXX', 10)[::-1] == [
        timesforge.times.history.Entry(action = 'archive', actor_id = 'UXXX2', target_id = 'UXXX1', channel_id = 'CXXX1', creation = CHANGE),
        timesforge.times.history.Entry(action = 'unarchive', actor_id = 'UXXX2', target_id = 'UXXX1', channel_id = 'CXXX1', creation = CHANGE),
        timesforge.times.history.Entry(action = 'rename', target_id = 'UXXX1', channel_id = 'CXXX1', details = {'channel_name': 'xxx'}, creation = CHANGE)
    ]
