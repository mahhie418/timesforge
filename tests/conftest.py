import collections.abc
import os
import pathlib

import pytest

import timesforge.storage

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[timesforge.storage.Database]:

    opening = timesforge.storage.Database(pathlib.Path(os.path.join(tmp_path, timesforge.storage.DATABASE_FILE))); yield opening
    opening.close()
