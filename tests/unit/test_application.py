import pathlib

import pytest

import timesforge.slack.application

def test_application_lock_exclusion(
    tmp_path: pathlib.Path
) -> None:

    with timesforge.slack.application.lock(tmp_path), pytest.raises(timesforge.slack.application.LockError, match = 'already running'), timesforge.slack.application.lock(tmp_path): pass
    with timesforge.slack.application.lock(tmp_path): pass
