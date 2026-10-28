import collections.abc
import datetime
import json
import os
import pathlib
import unittest.mock

import pytest
import slack_bolt
import slack_sdk

import timesforge.product
import timesforge.slack.api
import timesforge.slack.application
import timesforge.storage
import timesforge.terminal

CHANNELS_COUNT = 'SELECT count(*) FROM channel'

ENVIRONMENTS_START = [
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': 'xoxp-xxx', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX0'}, 0, '', ['xapp-xxx'], [('xoxb-xxx', True), ('xoxp-xxx', False), ('xoxb-xxx', False)]),
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': '', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX0'}, 0, '', ['xapp-xxx'], [('xoxb-xxx', True), ('xoxb-xxx', False), ('xoxb-xxx', False)]),
    ({'SLACK_APP_TOKEN': '', 'TIMESFORGE_OWNER_ID': '', 'TIMESFORGE_CHANNEL_ID_WELCOME': ''}, 1, 'error: Missing required environment variables: SLACK_APP_TOKEN, TIMESFORGE_OWNER_ID, TIMESFORGE_CHANNEL_ID_WELCOME\n', [], [])
]

def prepare(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    slack: slack_sdk.web.WebClient,
    mapping: object
) -> pathlib.Path:

    def connect(
        _: str
    ) -> slack_sdk.web.WebClient:

        return slack

    file = pathlib.Path(os.path.join(tmp_path, 'mapping.json'))
    file.write_text(json.dumps(mapping), encoding = 'utf-8')

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
    monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
    monkeypatch.setattr(timesforge.slack.api, 'connect', connect)

    return file

def count(
    directory: pathlib.Path
) -> int:

    database = timesforge.storage.Database(pathlib.Path(os.path.join(directory, timesforge.storage.DATABASE_FILE)))

    try: return database.connect().execute(CHANNELS_COUNT).fetchone()[0]
    finally: database.close()

def test_terminal_version_option(
    capsys: pytest.CaptureFixture[str]
) -> None:

    expected = f'{timesforge.product.COMMAND} {timesforge.product.VERSION}'

    with pytest.raises(SystemExit) as exception: timesforge.terminal.main(['--version'])

    assert exception.value.code == 0
    assert capsys.readouterr().out.strip() == expected

def test_terminal_command_missing(
    capsys: pytest.CaptureFixture[str]
) -> None:

    with pytest.raises(SystemExit) as exception: timesforge.terminal.main([])

    assert exception.value.code == 2
    assert 'required: <command>' in capsys.readouterr().err

class TestTerminalCommandImport:

    def test_preview(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        mapping = prepare(tmp_path, monkeypatch, slack, {'CXXX1': 'UXXX1'})

        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--dry-run']) == 0
        assert capsys.readouterr() == ('CXXX1 UXXX1: import\n', '')
        assert count(tmp_path) == 0

    def test_application(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        mapping = prepare(tmp_path, monkeypatch, slack, {'CXXX1': 'UXXX1'})

        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--apply']) == 0
        assert capsys.readouterr() == ('CXXX1 UXXX1: import\nchannels imported: 1\n', '')
        assert count(tmp_path) == 1
        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--apply']) == 0
        assert capsys.readouterr() == ('CXXX1 UXXX1: skip (registered)\nchannels imported: 0\n', '')

    def test_refusal(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        mapping = prepare(tmp_path, monkeypatch, slack, {'CXXX1': 'UXXX1', 'CXXX2': 'UXXX2'})

        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--apply']) == 1
        assert capsys.readouterr() == ('CXXX1 UXXX1: import\nCXXX2 UXXX2: error (name)\nnothing imported, because some channels cannot be\n', '')
        assert count(tmp_path) == 0

    def test_mapping(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        mapping = prepare(tmp_path, monkeypatch, slack, ['xxx'])

        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--dry-run']) == 1
        assert capsys.readouterr() == ('', f'error: {mapping} must hold one JSON object\n')

    def test_configuration(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        mapping = prepare(tmp_path, monkeypatch, slack, {'CXXX1': 'UXXX1'})
        monkeypatch.setenv('SLACK_BOT_TOKEN', '')

        assert timesforge.terminal.main(['import', '--mapping', str(mapping), '--dry-run']) == 1
        assert capsys.readouterr() == ('', 'error: Missing required environment variables: SLACK_BOT_TOKEN\n')

    def test_mode(
        self,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        with pytest.raises(SystemExit) as exception: timesforge.terminal.main(['import', '--mapping', 'xxx.json'])

        assert exception.value.code == 2
        assert 'one of the arguments --dry-run --apply is required' in capsys.readouterr().err

class TestTerminalCommandStart:

    @pytest.mark.parametrize(('environment', 'status', 'err', 'started', 'connected'), ENVIRONMENTS_START)
    def test_environment(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        environment: dict[str, str],
        status: int,
        err: str,
        started: list[str],
        connected: list[tuple[str, bool]]
    ) -> None:

        tokens = []
        connections = []

        def connect(
            token: str,
            *,
            idempotent: bool = True
        ) -> slack_sdk.web.WebClient:

            connections.append((token, idempotent))

            return slack

        def start(
            _: slack_bolt.App,
            token: str,
            recover: collections.abc.Callable[[str, datetime.datetime], None]
        ) -> None:

            tokens.append(token)
            recover('TXXX', datetime.datetime.now(datetime.UTC))

            raise KeyboardInterrupt

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.slack.application, 'start', start)

        for name, value in environment.items(): monkeypatch.setenv(name, value)

        assert timesforge.terminal.main(['start']) == status
        assert capsys.readouterr() == ('', err)
        assert tokens == started
        assert connections == connected

    def test_lock(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-xxx')
        monkeypatch.setenv('TIMESFORGE_OWNER_ID', 'UXXX1')
        monkeypatch.setenv('TIMESFORGE_CHANNEL_ID_WELCOME', 'CXXX0')
        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.slack.application, 'start', unittest.mock.Mock())

        with timesforge.slack.application.lock(tmp_path): assert timesforge.terminal.main(['start']) == 1
        assert capsys.readouterr() == ('', f'error: {timesforge.product.NAME} is already running with the data directory {tmp_path}\n')

class TestTerminalCommandManifest:

    def test_manifest(
        self,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        assert timesforge.terminal.main(['manifest']) == 0

        manifest = json.loads(capsys.readouterr().out)

        assert manifest['oauth_config']['scopes']['bot'] == ['channels:manage', 'channels:read', 'chat:write', 'im:history', 'im:write', 'users:read']
        assert manifest['oauth_config']['scopes']['user'] == ['channels:write']
        assert manifest['features']['app_home']['home_tab_enabled']
        assert manifest['settings']['event_subscriptions']['bot_events'] == ['app_home_opened', 'channel_archive', 'channel_deleted', 'channel_rename', 'channel_unarchive', 'member_joined_channel']
        assert manifest['settings']['interactivity']['is_enabled']
        assert manifest['settings']['socket_mode_enabled']
