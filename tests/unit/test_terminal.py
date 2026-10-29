import builtins
import collections.abc
import datetime
import getpass
import importlib.resources
import json
import os
import pathlib
import re
import sys
import typing
import unittest.mock
import urllib.parse
import webbrowser
import wsgiref.simple_server

import dotenv
import pytest
import slack_bolt
import slack_sdk
import slack_sdk.errors

import timesforge.autostart
import timesforge.product
import timesforge.shortener
import timesforge.slack.api
import timesforge.slack.application
import timesforge.storage
import timesforge.terminal
import timesforge.times.registry

CHANNELS_COUNT = 'SELECT count(*) FROM channel'

CREATION = datetime.datetime(2026, 10, 29, 15, 0, tzinfo = datetime.UTC)

ENVIRONMENTS_START = [
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': 'xoxp-xxx', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX0'}, 0, '', ['xapp-xxx'], [('xoxb-xxx', True), ('xoxp-xxx', False), ('xoxb-xxx', False)]),
    ({'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': '', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX0'}, 0, '', ['xapp-xxx'], [('xoxb-xxx', True), ('xoxb-xxx', False), ('xoxb-xxx', False)]),
    ({'SLACK_APP_TOKEN': '', 'TIMESFORGE_OWNER_ID': '', 'TIMESFORGE_CHANNEL_ID_WELCOME': ''}, 1, '[ERROR] Missing required environment variables: SLACK_APP_TOKEN, TIMESFORGE_OWNER_ID, TIMESFORGE_CHANNEL_ID_WELCOME\n', [], [])
]

REGISTRATIONS_STOP = [
    ('xxx', '[OK] autostart: removed xxx\n'),
    (None, '[OK] autostart: not registered\n')
]

ENVIRONMENT_DOCTOR = {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': 'xoxp-xxx', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}

CHECKS_DOCTOR = [
    ({}, 'UXXX2', 0, '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] user token: UXXX2\n[OK] database\n[OK] owner: xxx1\n[OK] welcome channel: #times_xxx\n', ''),
    ({'SLACK_USER_TOKEN': ''}, 'UXXX2', 0, '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] database\n[OK] owner: xxx1\n[OK] welcome channel: #times_xxx\n', ''),
    ({'SLACK_APP_TOKEN': ''}, 'UXXX2', 1, '', '[ERROR] Missing required environment variables: SLACK_APP_TOKEN\n'),
    ({}, 'UXXX1', 1, '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n', '[ERROR] SLACK_USER_TOKEN must belong to an admin of the workspace\n'),
    ({'TIMESFORGE_OWNER_ID': 'UXXX5'}, 'UXXX2', 1, '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] user token: UXXX2\n[OK] database\n', '[ERROR] UXXX5 is not a member of the workspace\n'),
    ({'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX2'}, 'UXXX2', 1, '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] user token: UXXX2\n[OK] database\n[OK] owner: xxx1\n', '[ERROR] The bot must be in #xxx to welcome new members\n')
]

TOKENS_SETUP = [
    (['xoxb-xxx', 'xapp-xxx', ''], '', 0, '[OK] Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['xapp-xxx', 'xoxb-xxx', '', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, '[OK] Slack: https://xxx.slack.com/\n', '\n[ERROR] SLACK_BOT_TOKEN must be a bot token starting with xoxb-\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['xoxb-xxx', 'xapp-xxx', 'xoxb-xxx', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, '[OK] Slack: https://xxx.slack.com/\n', '\n[ERROR] SLACK_USER_TOKEN must be a user token starting with xoxp-\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['', '', '', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, '[OK] Slack: https://xxx.slack.com/\n', '\n[ERROR] Missing required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['', '', ''], 'SLACK_BOT_TOKEN=xoxb-xxx\nSLACK_APP_TOKEN=xapp-xxx\n', 0, '[OK] Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    ([EOFError()], '', 1, '', '\n[ERROR] Setup was stopped\n', {})
]

OWNERS_SETUP = [
    (['UXXX2'], '[OK] owner: xxx2\n', '', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['xxx', 'UXXX2'], '[OK] owner: xxx2\n', '\n[ERROR] TIMESFORGE_OWNER_ID must be one Slack user ID\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['UXXX5', 'UXXX2'], '[OK] owner: xxx2\n', '\n[ERROR] UXXX5 is not a member of the workspace\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['UXXXB', 'UXXX2'], '[OK] owner: xxx2\n', '\n[ERROR] UXXXB is not a member of the workspace\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'})
]

CHANNELS_SETUP = [
    (['CXXX1'], '', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}),
    (['xxx', 'CXXX1'], '\n[ERROR] TIMESFORGE_CHANNEL_ID_WELCOME must be one Slack channel ID\n', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}),
    (['CXXX2', 'CXXX1'], '\n[ERROR] The bot must be in #xxx to welcome new members\n', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'})
]

CHANNELS_IMPORTED = [
    ([], "[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] database\n[OK] owner: xxx2\n[OK] welcome channel: #times_xxx\n[NEXT] import the times channels that members created by hand with 'timesforge import --mapping FILE': #times_xxx (CXXX1)\n\n"),
    ([timesforge.times.registry.Channel(channel_id = 'CXXX1', holder_id = 'UXXX1', first_name = 'xxx', channel_name = 'times_xxx', source = 'imported', creation = CREATION)], '[OK] settings ({file})\n[OK] Slack: https://xxx.slack.com/\n[OK] app-level token\n[OK] database\n[OK] owner: xxx2\n[OK] welcome channel: #times_xxx\n\n')
]

PLATFORMS_SETUP = [
    (frozenset({sys.platform}), [''], '[OK] autostart: xxx\n\n', 1),
    (frozenset({sys.platform}), ['yes'], '[OK] autostart: xxx\n\n', 1),
    (frozenset({sys.platform}), ['no'], "[NEXT] run 'timesforge start' to start the Slack app\n\n", 0),
    (frozenset[str](), [], "[NEXT] run 'timesforge start' to start the Slack app\n\n", 0)
]

LAYOUT_SETUP = """
timesforge (Version: {version})

Open the link below to create the Slack app. Its settings are filled in from the manifest.

>> http://127.0.0.1:0/slack

1. Choose the workspace, then follow the pages to create the app.
2. Choose Install to Workspace and allow the access the app asks for. Where only admins may create public channels, an admin does this.
3. In OAuth & Permissions, copy the Bot User OAuth Token (it starts with xoxb-), and the User OAuth Token (it starts with xoxp-) where only admins may create public channels.
4. In Basic Information, under App-Level Tokens, generate a token with the connections:write scope and copy it (it starts with xapp-).

Paste the Bot User OAuth Token and the App-Level Token, and the User OAuth Token where only admins may create public channels. They stay hidden as you type.

Bot User OAuth Token:
App-Level Token:
User OAuth Token:

[OK] Slack: https://xxx.slack.com/

Choose who owns timesforge in Slack, and copy their member ID.

1. In Slack, open their profile.
2. Choose ⋮ (More), then Copy member ID.

Member ID of the owner:

[OK] owner: xxx2

Choose the channel that new members join, such as #welcome, and copy its channel ID.

1. In Slack, open the channel and choose its name at the top.
2. At the bottom of About, copy the channel ID.
3. In the channel, send /invite @timesforge so that the bot joins it.

Channel ID of the welcome channel:

[OK] welcome channel: #times_xxx

[OK] settings ({file})
[OK] Slack: https://xxx.slack.com/
[OK] app-level token
[OK] database
[OK] owner: xxx2
[OK] welcome channel: #times_xxx
[NEXT] import the times channels that members created by hand with 'timesforge import --mapping FILE': #times_xxx (CXXX1)

Start the Slack app automatically when you log in? [Y/n]:

[NEXT] run 'timesforge start' to start the Slack app

"""

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

def answer(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tokens: collections.abc.Sequence[str | Exception] = ('xoxb-xxx', 'xapp-xxx', ''),
    owners: collections.abc.Sequence[str | Exception] = ('UXXX2',),
    channels: collections.abc.Sequence[str | Exception] = ('CXXX1',),
    starts: collections.abc.Sequence[str | Exception] = ('no',)
) -> unittest.mock.Mock:

    browse = unittest.mock.Mock()

    monkeypatch.setattr(getpass, 'getpass', unittest.mock.Mock(side_effect = tokens))
    monkeypatch.setattr(builtins, 'input', unittest.mock.Mock(side_effect = [*owners, *channels, *starts]))
    monkeypatch.setattr(webbrowser, 'open', browse)

    return browse

def extract(
    out: str,
    line: str
) -> str:

    lines = out.splitlines()

    return lines[lines.index(line) + 2].removeprefix('>> ')

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
        assert capsys.readouterr() == ('', f'[ERROR] {mapping} must hold one JSON object\n')

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
        assert capsys.readouterr() == ('', '[ERROR] Missing required environment variables: SLACK_BOT_TOKEN\n')

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

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-xxx')
        monkeypatch.setenv('TIMESFORGE_OWNER_ID', 'UXXX1')
        monkeypatch.setenv('TIMESFORGE_CHANNEL_ID_WELCOME', 'CXXX0')
        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.slack.application, 'start', unittest.mock.Mock())

        with timesforge.slack.application.lock(tmp_path): assert timesforge.terminal.main(['start']) == 1
        assert capsys.readouterr() == ('', f'[ERROR] {timesforge.product.NAME} is already running with the data directory {tmp_path}\n')

    def test_log(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient
    ) -> None:

        log = pathlib.Path(os.path.join(tmp_path, 'xxx', 'xxx.log'))

        def start(
            _: slack_bolt.App,
            token: str,
            recover: collections.abc.Callable[[str, datetime.datetime], None]
        ) -> None:

            sys.stdout.write(f'{token}\n')
            recover('TXXX', datetime.datetime.now(datetime.UTC))

            raise KeyboardInterrupt

        monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-xxx')
        monkeypatch.setenv('TIMESFORGE_OWNER_ID', 'UXXX1')
        monkeypatch.setenv('TIMESFORGE_CHANNEL_ID_WELCOME', 'CXXX0')
        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', unittest.mock.Mock(return_value = slack))
        monkeypatch.setattr(timesforge.slack.application, 'start', start)
        monkeypatch.setenv('SLACK_APP_TOKEN', '')

        assert timesforge.terminal.main(['start', '--log', str(log)]) == 1

        monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-xxx')

        assert timesforge.terminal.main(['start', '--log', str(log)]) == 0
        assert capsys.readouterr() == ('', '')
        assert log.read_text(encoding = 'utf-8') == '[ERROR] Missing required environment variables: SLACK_APP_TOKEN\nxapp-xxx\n'

class TestTerminalCommandStop:

    @pytest.mark.parametrize(('registration', 'out'), REGISTRATIONS_STOP)
    def test_registration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        registration: str | None,
        out: str
    ) -> None:

        monkeypatch.setattr(timesforge.autostart, 'unregister', unittest.mock.Mock(return_value = registration))

        assert timesforge.terminal.main(['stop']) == 0
        assert capsys.readouterr() == (out, '')

    def test_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]
    ) -> None:

        monkeypatch.setattr(timesforge.autostart, 'unregister', unittest.mock.Mock(side_effect = timesforge.autostart.AutostartError('xxx')))

        assert timesforge.terminal.main(['stop']) == 1
        assert capsys.readouterr() == ('', '[ERROR] xxx\n')

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

class TestTerminalCommandDoctor:

    @pytest.mark.parametrize(('environment', 'identity', 'status', 'out', 'err'), CHECKS_DOCTOR)
    def test_check(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        writer: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        environment: dict[str, str],
        identity: str,
        status: int,
        out: str,
        err: str
    ) -> None:

        def connect(
            token: str
        ) -> slack_sdk.web.WebClient:

            return writer if token.startswith('xoxp-') else slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(writer, 'auth_test', unittest.mock.Mock(return_value = {'user_id': identity}))

        for name, value in (ENVIRONMENT_DOCTOR | environment).items(): monkeypatch.setenv(name, value)

        assert timesforge.terminal.main(['doctor']) == status
        assert capsys.readouterr() == (out.format(file = configuration), err)

class TestTerminalCommandSetup:

    @pytest.mark.parametrize(('tokens', 'saved', 'status', 'out', 'err', 'written'), TOKENS_SETUP)
    def test_slack(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        tokens: list[str | Exception],
        saved: str,
        status: int,
        out: str,
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        def shorten(
            _: str,
            address: str
        ) -> str:

            return address

        manifest = json.loads(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))

        if saved:

            configuration.parent.mkdir()
            configuration.write_text(saved, encoding = 'utf-8')

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.shortener.Shortener, 'shorten', staticmethod(shorten))
        browse = answer(monkeypatch, tokens = tokens)

        assert timesforge.terminal.main(['setup']) == status

        captured = capsys.readouterr()
        url = extract(captured.out, 'Open the link below to create the Slack app. Its settings are filled in from the manifest.')

        assert not browse.called
        assert out in captured.out
        assert captured.err == err
        assert json.loads(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['manifest_json'][0]) == manifest
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name.startswith('SLACK_')} == written

    def test_refusal(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'apps_connections_open', unittest.mock.Mock(side_effect = [slack_sdk.errors.SlackApiError('xxx', 'xxx'), {'url': 'wss://xxx'}, {'url': 'wss://xxx'}]))
        answer(monkeypatch, tokens = ['xoxb-xxx', 'xapp-xxx1', '', 'xoxb-xxx', 'xapp-xxx2', ''])

        assert timesforge.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == '\n[ERROR] xxx\nThe server responded with: xxx\n'
        assert dotenv.dotenv_values(configuration)['SLACK_APP_TOKEN'] == 'xapp-xxx2'

    def test_admin(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        writer: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        def connect(
            token: str
        ) -> slack_sdk.web.WebClient:

            return writer if token.startswith('xoxp-') else slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(writer, 'auth_test', unittest.mock.Mock(side_effect = [{'user_id': 'UXXX1'}, {'user_id': 'UXXX2'}, {'user_id': 'UXXX2'}]))
        answer(monkeypatch, tokens = ['xoxb-xxx', 'xapp-xxx', 'xoxp-xxx1', 'xoxb-xxx', 'xapp-xxx', 'xoxp-xxx2'])

        assert timesforge.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == '\n[ERROR] SLACK_USER_TOKEN must belong to an admin of the workspace\n'
        assert dotenv.dotenv_values(configuration)['SLACK_USER_TOKEN'] == 'xoxp-xxx2'

    @pytest.mark.parametrize(('owners', 'out', 'err', 'written'), OWNERS_SETUP)
    def test_owner(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        owners: list[str],
        out: str,
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch, owners = owners)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert out in captured.out
        assert captured.err == err
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name == 'TIMESFORGE_OWNER_ID'} == written

    def test_profile(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'users_info', unittest.mock.Mock(return_value = {'user': {'id': 'UXXX2', 'name': 'xxx1', 'profile': {'display_name': '漢字', 'real_name': 'xxx2'}}}))
        answer(monkeypatch)

        assert timesforge.terminal.main(['setup']) == 0
        assert '[OK] owner: 漢字\n' in capsys.readouterr().out

    @pytest.mark.parametrize(('channels', 'err', 'written'), CHANNELS_SETUP)
    def test_channel(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path,
        channels: list[str],
        err: str,
        written: dict[str, str]
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch, channels = channels)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert '[OK] welcome channel: #times_xxx\n' in captured.out
        assert captured.err == err
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name == 'TIMESFORGE_CHANNEL_ID_WELCOME'} == written

    def test_invitation(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'conversations_info', unittest.mock.Mock(side_effect = [{'channel': {'id': 'CXXX3', 'name': 'xxx'}}, {'channel': {'id': 'CXXX3', 'name': 'xxx', 'is_member': True}}, {'channel': {'id': 'CXXX3', 'name': 'xxx', 'is_member': True}}]))
        answer(monkeypatch, channels = ['CXXX3', ''])

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert '[OK] welcome channel: #xxx\n' in captured.out
        assert captured.err == '\n[ERROR] The bot must be in #xxx to welcome new members\n'
        assert dotenv.dotenv_values(configuration)['TIMESFORGE_CHANNEL_ID_WELCOME'] == 'CXXX3'

    @pytest.mark.parametrize(('channels', 'out'), CHANNELS_IMPORTED)
    def test_check(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        database: timesforge.storage.Database,
        configuration: pathlib.Path,
        channels: list[timesforge.times.registry.Channel],
        out: str
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        registry = timesforge.times.registry.RegistryIO(database)

        for channel in channels: registry.save('TXXX', channel)

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert out.format(file = configuration) in captured.out
        assert not captured.err

    @pytest.mark.parametrize(('platforms', 'starts', 'out', 'registrations'), PLATFORMS_SETUP)
    def test_autostart(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        platforms: frozenset[str],
        starts: list[str],
        out: str,
        registrations: int
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        register = unittest.mock.Mock(return_value = 'xxx')

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.autostart, 'register', register)
        monkeypatch.setattr(timesforge.autostart, 'PLATFORMS', platforms)
        answer(monkeypatch, starts = starts)

        assert timesforge.terminal.main(['setup']) == 0
        assert capsys.readouterr().out.endswith(out)
        assert register.call_args_list == [unittest.mock.call(pathlib.Path(os.path.join(tmp_path, 'start.log')))] * registrations

    def test_failure(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        register = unittest.mock.Mock()

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(timesforge.storage, 'Database', unittest.mock.Mock(side_effect = timesforge.storage.DatabaseError('xxx')))
        monkeypatch.setattr(timesforge.autostart, 'register', register)
        monkeypatch.setattr(timesforge.autostart, 'PLATFORMS', frozenset({sys.platform}))
        answer(monkeypatch, starts = [''])

        assert timesforge.terminal.main(['setup']) == 1
        assert capsys.readouterr().err == '[ERROR] xxx\n'
        assert not register.called

    def test_link(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/slack', extract(captured.out, 'Open the link below to create the Slack app. Its settings are filled in from the manifest.'))
        assert captured.err == ''

    def test_warning(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(wsgiref.simple_server, 'make_server', unittest.mock.Mock(side_effect = OSError('xxx')))
        answer(monkeypatch)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert captured.err == '\n[WARNING] Short links are not available on this computer (xxx), so the full address follows\n'
        assert extract(captured.out, 'Open the link below to create the Slack app. Its settings are filled in from the manifest.').startswith('https://api.slack.com/apps?new_app=1&manifest_json=')

    def test_layout(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        workspace: dict[str, typing.Any],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        answers = ['xoxb-xxx', 'xapp-xxx', '', 'UXXX2', 'CXXX1', 'no']

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        def enter(
            prompt: str
        ) -> str:

            sys.stdout.write(f'{prompt.rstrip()}\n')

            return answers.pop(0)

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setenv('TIMESFORGE_DATA_DIRECTORY', str(tmp_path))
        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(getpass, 'getpass', enter)
        monkeypatch.setattr(builtins, 'input', enter)
        monkeypatch.setattr(timesforge.autostart, 'PLATFORMS', frozenset({sys.platform}))

        assert timesforge.terminal.main(['setup']) == 0
        assert re.sub(r'http://127\.0\.0\.1:[0-9]+/', 'http://127.0.0.1:0/', capsys.readouterr().out) == LAYOUT_SETUP.format(version = timesforge.product.VERSION, file = configuration)
