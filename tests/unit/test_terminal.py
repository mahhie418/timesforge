import builtins
import collections.abc
import datetime
import getpass
import importlib.resources
import json
import os
import pathlib
import typing
import unittest.mock
import urllib.parse
import webbrowser

import dotenv
import pytest
import slack_bolt
import slack_sdk
import slack_sdk.errors

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

ENVIRONMENT_DOCTOR = {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': 'xoxp-xxx', 'TIMESFORGE_OWNER_ID': 'UXXX1', 'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}

CHECKS_DOCTOR = [
    ({}, 'UXXX2', 0, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: app-level token\nok: user token: UXXX2\nok: database\nok: owner: xxx1\nok: welcome channel: #times_xxx\n', ''),
    ({'SLACK_USER_TOKEN': ''}, 'UXXX2', 0, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: app-level token\nok: database\nok: owner: xxx1\nok: welcome channel: #times_xxx\n', ''),
    ({'SLACK_APP_TOKEN': ''}, 'UXXX2', 1, '', 'error: Missing required environment variables: SLACK_APP_TOKEN\n'),
    ({}, 'UXXX1', 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: app-level token\n', 'error: SLACK_USER_TOKEN must belong to an admin of the workspace\n'),
    ({'TIMESFORGE_OWNER_ID': 'UXXX5'}, 'UXXX2', 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: app-level token\nok: user token: UXXX2\nok: database\n', 'error: UXXX5 is not a member of the workspace\n'),
    ({'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX2'}, 'UXXX2', 1, 'ok: settings ({file})\nok: Slack: https://xxx.slack.com/\nok: app-level token\nok: user token: UXXX2\nok: database\nok: owner: xxx1\n', 'error: The bot must be in #xxx to welcome new members\n')
]

TOKENS_SETUP = [
    (['xoxb-xxx', 'xapp-xxx', ''], '', 0, 'ok: Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['xapp-xxx', 'xoxb-xxx', '', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, 'ok: Slack: https://xxx.slack.com/\n', 'error: SLACK_BOT_TOKEN must be a bot token starting with xoxb-\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['xoxb-xxx', 'xapp-xxx', 'xoxb-xxx', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, 'ok: Slack: https://xxx.slack.com/\n', 'error: SLACK_USER_TOKEN must be a user token starting with xoxp-\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['', '', '', 'xoxb-xxx', 'xapp-xxx', ''], '', 0, 'ok: Slack: https://xxx.slack.com/\n', 'error: Missing required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN\n', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    (['', '', ''], 'SLACK_BOT_TOKEN=xoxb-xxx\nSLACK_APP_TOKEN=xapp-xxx\n', 0, 'ok: Slack: https://xxx.slack.com/\n', '', {'SLACK_BOT_TOKEN': 'xoxb-xxx', 'SLACK_APP_TOKEN': 'xapp-xxx', 'SLACK_USER_TOKEN': ''}),
    ([EOFError()], '', 1, '', '\nerror: Setup was stopped\n', {})
]

OWNERS_SETUP = [
    (['UXXX2'], 'ok: owner: xxx2\n', '', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['xxx', 'UXXX2'], 'ok: owner: xxx2\n', 'error: TIMESFORGE_OWNER_ID must be one Slack user ID\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['UXXX5', 'UXXX2'], 'ok: owner: xxx2\n', 'error: UXXX5 is not a member of the workspace\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'}),
    (['UXXXB', 'UXXX2'], 'ok: owner: xxx2\n', 'error: UXXXB is not a member of the workspace\n', {'TIMESFORGE_OWNER_ID': 'UXXX2'})
]

CHANNELS_SETUP = [
    (['CXXX1'], '', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}),
    (['xxx', 'CXXX1'], 'error: TIMESFORGE_CHANNEL_ID_WELCOME must be one Slack channel ID\n', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'}),
    (['CXXX2', 'CXXX1'], 'error: The bot must be in #xxx to welcome new members\n', {'TIMESFORGE_CHANNEL_ID_WELCOME': 'CXXX1'})
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
    channels: collections.abc.Sequence[str | Exception] = ('CXXX1',)
) -> unittest.mock.Mock:

    browse = unittest.mock.Mock()

    monkeypatch.setattr(getpass, 'getpass', unittest.mock.Mock(side_effect = tokens))
    monkeypatch.setattr(builtins, 'input', unittest.mock.Mock(side_effect = [*owners, *channels]))
    monkeypatch.setattr(webbrowser, 'open', browse)

    return browse

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

        manifest = json.loads(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))

        if saved:

            configuration.parent.mkdir()
            configuration.write_text(saved, encoding = 'utf-8')

        workspace['channels'][0]['is_member'] = True

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        browse = answer(monkeypatch, tokens = tokens)

        assert timesforge.terminal.main(['setup']) == status

        captured = capsys.readouterr()
        url: str = browse.call_args_list[0].args[0]

        assert out in captured.out
        assert captured.err == err
        assert json.loads(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['manifest_json'][0]) == manifest
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name.startswith('SLACK_')} == written

    def test_refusal(
        self,
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

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'apps_connections_open', unittest.mock.Mock(side_effect = [slack_sdk.errors.SlackApiError('xxx', 'xxx'), {'url': 'wss://xxx'}]))
        answer(monkeypatch, tokens = ['xoxb-xxx', 'xapp-xxx1', '', 'xoxb-xxx', 'xapp-xxx2', ''])

        assert timesforge.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == 'error: xxx\nThe server responded with: xxx\n'
        assert dotenv.dotenv_values(configuration)['SLACK_APP_TOKEN'] == 'xapp-xxx2'

    def test_admin(
        self,
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

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(writer, 'auth_test', unittest.mock.Mock(side_effect = [{'user_id': 'UXXX1'}, {'user_id': 'UXXX2'}]))
        answer(monkeypatch, tokens = ['xoxb-xxx', 'xapp-xxx', 'xoxp-xxx1', 'xoxb-xxx', 'xapp-xxx', 'xoxp-xxx2'])

        assert timesforge.terminal.main(['setup']) == 0
        assert capsys.readouterr().err == 'error: SLACK_USER_TOKEN must belong to an admin of the workspace\n'
        assert dotenv.dotenv_values(configuration)['SLACK_USER_TOKEN'] == 'xoxp-xxx2'

    @pytest.mark.parametrize(('owners', 'out', 'err', 'written'), OWNERS_SETUP)
    def test_owner(
        self,
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

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch, owners = owners)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert out in captured.out
        assert captured.err == err
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name == 'TIMESFORGE_OWNER_ID'} == written

    def test_profile(
        self,
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

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'users_info', unittest.mock.Mock(return_value = {'user': {'id': 'UXXX2', 'name': 'xxx1', 'profile': {'display_name': '漢字', 'real_name': 'xxx2'}}}))
        answer(monkeypatch)

        assert timesforge.terminal.main(['setup']) == 0
        assert 'ok: owner: 漢字\n' in capsys.readouterr().out

    @pytest.mark.parametrize(('channels', 'err', 'written'), CHANNELS_SETUP)
    def test_channel(
        self,
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

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        answer(monkeypatch, channels = channels)

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert captured.out.endswith('ok: welcome channel: #times_xxx\n')
        assert captured.err == err
        assert {name: value for name, value in dotenv.dotenv_values(configuration).items() if name == 'TIMESFORGE_CHANNEL_ID_WELCOME'} == written

    def test_invitation(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        slack: slack_sdk.web.WebClient,
        configuration: pathlib.Path
    ) -> None:

        def connect(
            _: str
        ) -> slack_sdk.web.WebClient:

            return slack

        monkeypatch.setattr(timesforge.slack.api, 'connect', connect)
        monkeypatch.setattr(slack, 'conversations_info', unittest.mock.Mock(side_effect = [{'channel': {'id': 'CXXX3', 'name': 'xxx'}}, {'channel': {'id': 'CXXX3', 'name': 'xxx', 'is_member': True}}]))
        answer(monkeypatch, channels = ['CXXX3', ''])

        assert timesforge.terminal.main(['setup']) == 0

        captured = capsys.readouterr()

        assert captured.out.endswith('ok: welcome channel: #xxx\n')
        assert captured.err == 'error: The bot must be in #xxx to welcome new members\n'
        assert dotenv.dotenv_values(configuration)['TIMESFORGE_CHANNEL_ID_WELCOME'] == 'CXXX3'
