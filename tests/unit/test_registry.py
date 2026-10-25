import dataclasses
import datetime

import timesforge.storage
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

def create(
    channel_id: str,
    holder_id: str,
    creation: datetime.datetime = CREATION
) -> timesforge.times.registry.Channel:

    return timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = f'times_{channel_id.lower()}', creation = creation)

def test_registry_channel_saving(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert store.load('TXXX', 'CXXX1') == channel

def test_registry_channel_missing(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert store.load('TXXX', 'CXXX2') is None
    assert store.load('TYYY', 'CXXX1') is None

def test_registry_holder_channel(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channels = [create('CXXX2', 'UXXX1', CHANGE), create('CXXX1', 'UXXX1')]

    for channel in [*channels, create('CXXX3', 'UXXX2')]: store.save('TXXX', channel)

    store.save('TYYY', create('CXXX4', 'UXXX1'))

    assert store.find('TXXX', 'UXXX1') == channels[::-1]
    assert store.find('TXXX', 'UXXX3') == []

def test_registry_lifecycle_archival(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert store.archive('TXXX', 'CXXX1', CHANGE)
    assert not store.archive('TXXX', 'CXXX1', CHANGE)
    assert store.load('TXXX', 'CXXX1') == dataclasses.replace(channel, status = 'archived', archival = CHANGE)

def test_registry_lifecycle_restoration(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert not store.unarchive('TXXX', 'CXXX1', CHANGE)

    store.archive('TXXX', 'CXXX1', CHANGE)

    assert store.unarchive('TXXX', 'CXXX1', CHANGE)
    assert store.load('TXXX', 'CXXX1') == channel

def test_registry_lifecycle_renaming(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert store.rename('TXXX', 'CXXX1', 'xxx', CHANGE)
    assert not store.rename('TXXX', 'CXXX1', 'xxx', CHANGE)
    assert store.load('TXXX', 'CXXX1') == dataclasses.replace(channel, channel_name = 'xxx')

def test_registry_lifecycle_deletion(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)
    store.archive('TXXX', 'CXXX1', CREATION)

    assert store.delete('TXXX', 'CXXX1', CHANGE)
    assert not store.delete('TXXX', 'CXXX1', CHANGE)
    assert not store.unarchive('TXXX', 'CXXX1', CHANGE)
    assert not store.archive('TXXX', 'CXXX1', CHANGE)
    assert not store.rename('TXXX', 'CXXX1', 'xxx', CHANGE)
    assert store.load('TXXX', 'CXXX1') == dataclasses.replace(channel, status = 'deleted', archival = CREATION, deletion = CHANGE)

def test_registry_lifecycle_unknown(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.registry.RegistryIO(database)
    channel = create('CXXX1', 'UXXX1')

    store.save('TXXX', channel)

    assert not store.archive('TXXX', 'CXXX2', CHANGE)
    assert not store.rename('TYYY', 'CXXX1', 'xxx', CHANGE)
    assert not store.delete('TYYY', 'CXXX1', CHANGE)
    assert store.load('TXXX', 'CXXX1') == create('CXXX1', 'UXXX1')
