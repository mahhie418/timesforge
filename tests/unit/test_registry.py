import datetime

import timesforge.storage
import timesforge.times.registry

CREATION = datetime.datetime(2026, 10, 9, 15, 0, tzinfo = datetime.UTC)

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
    channels = [create('CXXX2', 'UXXX1', CREATION + datetime.timedelta(days = 1)), create('CXXX1', 'UXXX1')]

    for channel in [*channels, create('CXXX3', 'UXXX2')]: store.save('TXXX', channel)

    store.save('TYYY', create('CXXX4', 'UXXX1'))

    assert store.find('TXXX', 'UXXX1') == channels[::-1]
    assert store.find('TXXX', 'UXXX3') == []
