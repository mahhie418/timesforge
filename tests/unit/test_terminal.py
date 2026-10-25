import json
import os
import pathlib

import pytest
import slack_sdk

import timesforge.product
import timesforge.slack.api
import timesforge.storage
import timesforge.terminal

CHANNELS_COUNT = 'SELECT count(*) FROM channel'

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

def test_terminal_version(
    capsys: pytest.CaptureFixture[str]
) -> None:

    expected = f'{timesforge.product.COMMAND} {timesforge.product.VERSION}'

    with pytest.raises(SystemExit) as exception: timesforge.terminal.main(['--version'])

    assert exception.value.code == 0
    assert capsys.readouterr().out.strip() == expected

def test_terminal_missing(
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
