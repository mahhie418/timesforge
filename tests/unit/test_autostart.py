import os
import pathlib
import plistlib
import subprocess
import sys
import unittest.mock

import pytest

import timesforge.autostart

def test_autostart_agent_registration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    log = pathlib.Path(os.path.join(tmp_path, 'xxx&xxx.log'))
    run = unittest.mock.Mock()

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', run)

    agent = pathlib.Path(timesforge.autostart.register(log))

    assert agent == pathlib.Path(os.path.join(tmp_path, 'Library', 'LaunchAgents', 'timesforge.plist'))
    assert plistlib.loads(agent.read_bytes()) == {'Label': 'timesforge', 'ProgramArguments': [sys.executable, '-m', 'timesforge', 'start'], 'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False}, 'StandardOutPath': str(log), 'StandardErrorPath': str(log)}
    assert [call.args[0] for call in run.call_args_list] == [['/bin/launchctl', 'bootout', 'gui/501/timesforge'], ['/bin/launchctl', 'bootstrap', 'gui/501', str(agent)]]

def test_autostart_agent_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', unittest.mock.Mock(side_effect = [None, subprocess.CalledProcessError(5, 'xxx', stderr = 'xxx\n')]))

    with pytest.raises(timesforge.autostart.AutostartError, match = r'refused .*timesforge\.plist: xxx$'): timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_platform_support() -> None:

    assert sorted(timesforge.autostart.PLATFORMS) == ['darwin']

def test_autostart_platform_rejection(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'xxx')

    with pytest.raises(timesforge.autostart.AutostartError, match = r'not supported on xxx$'): timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))
