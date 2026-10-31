# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import collections.abc
import os
import pathlib
import threading

import pytest

import timesforge.storage

MIGRATIONS = (
    ('CREATE TABLE xxx (value TEXT NOT NULL) STRICT',),
    ('CREATE TABLE yyy (value TEXT NOT NULL) STRICT', 'INSERT INTO yyy SELECT value FROM xxx')
)

INSERT = "INSERT INTO xxx VALUES ('xxx')"
COUNTS = {'xxx': 'SELECT count(*) FROM xxx', 'yyy': 'SELECT count(*) FROM yyy'}

@pytest.fixture(autouse = True)
def migrations(
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(timesforge.storage, '_MIGRATIONS', MIGRATIONS[:1])

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[timesforge.storage.Database]:

    opening = timesforge.storage.Database(pathlib.Path(os.path.join(tmp_path, 'xxx', timesforge.storage.DATABASE_FILE))); yield opening
    opening.close()

def count(
    database: timesforge.storage.Database,
    table: str = 'xxx'
) -> int:

    return database.connect().execute(COUNTS[table]).fetchone()[0]

def insert(
    database: timesforge.storage.Database
) -> None:

    with database.begin() as connection: connection.execute(INSERT); raise RuntimeError('xxx')

def test_storage_database_creation(
    database: timesforge.storage.Database
) -> None:

    connection = database.connect()
    rows = connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'").fetchall()

    assert {row['name'] for row in rows} == {'xxx'}
    assert connection.execute('PRAGMA user_version').fetchone()[0] == 1

def test_storage_database_migration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, timesforge.storage.DATABASE_FILE))
    opening = timesforge.storage.Database(path)

    with opening.begin() as connection: connection.execute(INSERT)

    opening.close()

    monkeypatch.setattr(timesforge.storage, '_MIGRATIONS', MIGRATIONS)
    upgrade = timesforge.storage.Database(path)

    try:

        assert upgrade.connect().execute('PRAGMA user_version').fetchone()[0] == 2
        assert count(upgrade, 'xxx') == 1
        assert count(upgrade, 'yyy') == 1

    finally:

        upgrade.close()

def test_storage_database_connection(
    database: timesforge.storage.Database
) -> None:

    connection = database.connect()

    assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1

def test_storage_database_consistency(
    database: timesforge.storage.Database
) -> None:

    connections = []

    def work() -> None:

        connections.append(database.connect())
        database.close()

    worker = threading.Thread(target = work)
    worker.start()
    worker.join()

    assert len(connections) == 1
    assert connections[0] is not database.connect()

def test_storage_database_robustness(
    tmp_path: pathlib.Path
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, timesforge.storage.DATABASE_FILE))
    databases = [timesforge.storage.Database(path) for _ in range(2)]

    with databases[0].begin() as connection: connection.execute(INSERT)

    databases[0].close()

    try: assert count(databases[1]) == 1
    finally: databases[1].close()

def test_storage_database_exception(
    database: timesforge.storage.Database
) -> None:

    with pytest.raises(RuntimeError, match = 'xxx'): insert(database)

    assert count(database) == 0

def test_storage_database_version(
    tmp_path: pathlib.Path
) -> None:

    path = pathlib.Path(os.path.join(tmp_path, timesforge.storage.DATABASE_FILE))
    opening = timesforge.storage.Database(path)

    connection = opening.connect()
    connection.execute('PRAGMA user_version = 999')

    opening.close()

    with pytest.raises(timesforge.storage.DatabaseError, match = 'newer version'): timesforge.storage.Database(path)

def test_storage_directory_creation(
    tmp_path: pathlib.Path,
    database: timesforge.storage.Database
) -> None:

    expected = pathlib.Path(os.path.join(tmp_path, 'xxx', timesforge.storage.DATABASE_FILE))

    assert database.path == expected
    assert database.path.is_file()
