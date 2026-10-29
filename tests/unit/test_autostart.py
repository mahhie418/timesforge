import os
import pathlib
import plistlib
import subprocess
import sys
import unittest.mock
import xml.sax.saxutils

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

def test_autostart_task_registration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    log = pathlib.Path(os.path.join(tmp_path, 'xxx xxx.log'))
    run = unittest.mock.Mock()
    python = xml.sax.saxutils.escape(str(pathlib.Path(sys.executable).with_name('pythonw.exe')))

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('SYSTEMROOT', 'xxx')
    monkeypatch.setenv('USERDOMAIN', 'xxx1')
    monkeypatch.setenv('USERNAME', 'xxx2')
    monkeypatch.setattr(subprocess, 'run', run)

    task = pathlib.Path(timesforge.autostart.register(log))
    text = task.read_text(encoding = 'utf-16')

    assert task == pathlib.Path(os.path.join(tmp_path, 'timesforge.xml'))
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n')
    assert '<LogonTrigger>\n      <UserId>xxx1\\xxx2</UserId>\n    </LogonTrigger>' in text
    assert '<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>' in text
    assert '<RestartOnFailure>\n      <Interval>PT1M</Interval>\n      <Count>999</Count>\n    </RestartOnFailure>' in text
    assert f'<Exec>\n      <Command>{python}</Command>\n      <Arguments>-m timesforge start --log "{log}"</Arguments>\n    </Exec>' in text

    command = os.path.join('xxx', 'System32', 'schtasks.exe')

    assert [call.args[0] for call in run.call_args_list] == [[command, '/Create', '/TN', 'timesforge', '/XML', str(task), '/F'], [command, '/End', '/TN', 'timesforge'], [command, '/Run', '/TN', 'timesforge']]

def test_autostart_task_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', unittest.mock.Mock(side_effect = subprocess.CalledProcessError(1, 'xxx', stderr = 'xxx\n')))

    with pytest.raises(timesforge.autostart.AutostartError, match = r'refused .*timesforge\.xml: xxx$'): timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_start_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(side_effect = [None, None, subprocess.CalledProcessError(1, 'xxx', stderr = 'xxx\n')])
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', run)

    with pytest.raises(timesforge.autostart.AutostartError, match = 'could not start timesforge: xxx'): timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_end_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(side_effect = [None, subprocess.CompletedProcess('xxx', 1), None])
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', run)
    timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

    assert run.call_args_list[-1].args[0][1:] == ['/Run', '/TN', 'timesforge']
    assert len(run.call_args_list) == 3

def test_autostart_agent_removal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    agent = pathlib.Path(os.path.join(tmp_path, 'Library', 'LaunchAgents', 'timesforge.plist'))
    agent.parent.mkdir(parents = True)
    agent.write_text('xxx', encoding = 'utf-8')
    run = unittest.mock.Mock()

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', run)

    assert timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log'))) == str(agent)
    assert not agent.exists()
    assert [call.args[0] for call in run.call_args_list] == [['/bin/launchctl', 'bootout', 'gui/501/timesforge']]

def test_autostart_agent_absence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(return_value = subprocess.CompletedProcess('xxx', 3))

    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(os, 'getuid', lambda: 501, raising = False)
    monkeypatch.setattr(pathlib.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(subprocess, 'run', run)

    assert timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log'))) is None
    assert [call.args[0] for call in run.call_args_list] == [['/bin/launchctl', 'bootout', 'gui/501/timesforge']]

def test_autostart_task_removal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    task = pathlib.Path(os.path.join(tmp_path, 'timesforge.xml'))
    task.write_text('xxx', encoding = 'utf-16')
    run = unittest.mock.Mock(return_value = subprocess.CompletedProcess('xxx', 0))

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('SYSTEMROOT', 'xxx')
    monkeypatch.setattr(subprocess, 'run', run)

    assert timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log'))) == str(task)
    assert not task.exists()

    command = os.path.join('xxx', 'System32', 'schtasks.exe')

    assert [call.args[0] for call in run.call_args_list] == [[command, '/Query', '/TN', 'timesforge'], [command, '/End', '/TN', 'timesforge'], [command, '/Delete', '/TN', 'timesforge', '/F']]

def test_autostart_task_absence(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    run = unittest.mock.Mock(return_value = subprocess.CompletedProcess('xxx', 1))

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', run)

    assert timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log'))) is None
    assert [call.args[0][1:] for call in run.call_args_list] == [['/Query', '/TN', 'timesforge']]

def test_autostart_deletion_refusal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    task = pathlib.Path(os.path.join(tmp_path, 'timesforge.xml'))
    task.write_text('xxx', encoding = 'utf-16')

    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(subprocess, 'run', unittest.mock.Mock(side_effect = [subprocess.CompletedProcess('xxx', 0), subprocess.CompletedProcess('xxx', 0), subprocess.CalledProcessError(1, 'xxx', stderr = 'xxx\n')]))

    with pytest.raises(timesforge.autostart.AutostartError, match = 'refused to delete timesforge: xxx'): timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

    assert task.exists()

def test_autostart_platform_support() -> None:

    assert sorted(timesforge.autostart.PLATFORMS) == ['darwin', 'win32']

def test_autostart_platform_rejection(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'xxx')

    with pytest.raises(timesforge.autostart.AutostartError, match = r'not supported on xxx$'): timesforge.autostart.register(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))

def test_autostart_removal_rejection(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(sys, 'platform', 'xxx')

    with pytest.raises(timesforge.autostart.AutostartError, match = r'not supported on xxx$'): timesforge.autostart.unregister(pathlib.Path(os.path.join(tmp_path, 'xxx.log')))
