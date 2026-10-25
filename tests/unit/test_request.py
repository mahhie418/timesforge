import datetime
import threading

import pytest

import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.naming
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

CREATION = datetime.datetime(2026, 10, 25, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(days = 1)

REFUSALS = [('UXXX1', 'holder'), ('UXXX2', 'used'), ('UXXX3', 'excluded')]
REQUESTS_COUNT = 'SELECT count(*) FROM request'

def register(
    database: timesforge.storage.Database,
    channel_id: str,
    holder_id: str
) -> timesforge.times.registry.RegistryIO:

    store = timesforge.times.registry.RegistryIO(database)
    channel = timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = 'Xxx', channel_name = 'times_xxx', creation = CREATION)

    store.save('TXXX', channel)

    return store

def run(
    targets: list[tuple[str, str]],
    store: timesforge.times.request.RequestIO
) -> list[timesforge.times.request.Request]:

    requests = []
    barrier = threading.Barrier(len(targets))

    def reserve(
        user_id: str,
        first_name: str
    ) -> None:

        barrier.wait()
        requests.append(store.reserve('TXXX', user_id, first_name, CREATION))

    threads = [threading.Thread(target = reserve, args = target) for target in targets]

    for thread in threads: thread.start()
    for thread in threads: thread.join()

    return requests

def test_request_channel_reservation(
    database: timesforge.storage.Database
) -> None:

    request = timesforge.times.request.RequestIO(database).reserve('TXXX', 'UXXX1', ' Xxx ', CREATION)

    assert request == timesforge.times.request.Request(request_id = request.request_id, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'reserved', grant_id = None, creation = CREATION)

def test_request_channel_repetition(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.request.RequestIO(database)

    request = store.reserve('TXXX', 'UXXX1', 'Xxx', CREATION)

    assert store.reserve('TXXX', 'UXXX1', 'Yyy', CHANGE) == request
    assert store.reserve('TYYY', 'UXXX1', 'Yyy', CHANGE) != request
    assert database.connect().execute(REQUESTS_COUNT).fetchone()[0] == 2

def test_request_channel_concurrency(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.request.RequestIO(database)

    requests = run([('UXXX1', 'Xxx')] * 8, store)

    assert len(requests) == 8
    assert {request.request_id for request in requests} == {requests[0].request_id}

    requests = run([('UXXX2', 'Yyy'), ('UXXX3', 'Yyy')], store)

    assert sorted(request.status for request in requests) == ['pending_name_resolution', 'reserved']
    assert database.connect().execute(REQUESTS_COUNT).fetchone()[0] == 3

def test_request_name_conflict(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1')
    register(database, 'CXXX2', 'UXXX2').delete('TXXX', 'CXXX2', CREATION)

    store = timesforge.times.request.RequestIO(database)

    assert store.reserve('TXXX', 'UXXX3', 'Xxx', CREATION).status == 'pending_name_resolution'
    assert store.reserve('TYYY', 'UXXX3', 'Xxx', CREATION).status == 'reserved'

    timesforge.times.registry.RegistryIO(database).archive('TXXX', 'CXXX1', CREATION)

    assert store.reserve('TXXX', 'UXXX4', 'Yyy', CREATION).status == 'reserved'
    assert store.reserve('TXXX', 'UXXX5', 'Yyy', CREATION).status == 'pending_name_resolution'

@pytest.mark.parametrize(('user_id', 'expected'), REFUSALS)
def test_request_member_refusal(
    database: timesforge.storage.Database,
    user_id: str,
    expected: str
) -> None:

    register(database, 'CXXX1', 'UXXX1')
    register(database, 'CXXX2', 'UXXX2').delete('TXXX', 'CXXX2', CREATION)

    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', timesforge.times.exclusion.Exclusion(user_id = 'UXXX3', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION))

    with pytest.raises(timesforge.times.request.RequestRefusedError) as exception: timesforge.times.request.RequestIO(database).reserve('TXXX', user_id, 'Yyy', CREATION)

    assert exception.value.refusal == expected
    assert database.connect().execute(REQUESTS_COUNT).fetchone()[0] == 0

def test_request_grant_reservation(
    database: timesforge.storage.Database
) -> None:

    register(database, 'CXXX1', 'UXXX1').delete('TXXX', 'CXXX1', CREATION)

    grants = timesforge.times.recreation.RecreationIO(database)
    grant = grants.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CREATION)

    request = timesforge.times.request.RequestIO(database).reserve('TXXX', 'UXXX1', 'Yyy', CHANGE)

    assert request.grant_id == grant.grant_id
    assert [(item.status, item.reservation) for item in grants.find('TXXX', 'UXXX1')] == [('reserved', CHANGE)]

    with pytest.raises(timesforge.times.recreation.GrantInvalidError) as exception: grants.grant('TXXX', 'UXXX1', owner_id = 'UXXX0', now = CHANGE)

    assert exception.value.reason == 'grant'
    assert grants.consume('TXXX', 'UXXX1', 'CXXX2', CHANGE)

def test_request_name_invalid(
    database: timesforge.storage.Database
) -> None:

    with pytest.raises(timesforge.times.naming.NameInvalidError): timesforge.times.request.RequestIO(database).reserve('TXXX', 'UXXX1', 'xxx yyy', CREATION)

    assert database.connect().execute(REQUESTS_COUNT).fetchone()[0] == 0

def test_request_status_transition(
    database: timesforge.storage.Database
) -> None:

    store = timesforge.times.request.RequestIO(database)

    request = store.reserve('TXXX', 'UXXX1', 'Xxx', CREATION)

    assert not store.retry('TXXX', request.request_id, CHANGE)
    assert not store.lose('TXXX', request.request_id, error = 'xxx', now = CHANGE)
    assert store.start('TXXX', request.request_id, CHANGE)
    assert not store.start('TXXX', request.request_id, CHANGE)
    assert store.lose('TXXX', request.request_id, error = 'xxx', now = CHANGE)
    assert not store.postpone('TXXX', request.request_id, CHANGE)
    assert store.retry('TXXX', request.request_id, CHANGE)
    assert store.fail('TXXX', request.request_id, error = 'yyy', now = CHANGE)
    assert not store.fail('TXXX', request.request_id, error = 'yyy', now = CHANGE)
    assert store.load('TXXX', request.request_id) == timesforge.times.request.Request(request_id = request.request_id, user_id = 'UXXX1', first_name = 'Xxx', channel_name = 'times_xxx', status = 'failed', grant_id = None, error = 'yyy', creation = CREATION)
    assert store.load('TXXX', request.request_id + 1) is None
