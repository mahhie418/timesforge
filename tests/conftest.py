import collections.abc
import json
import os
import pathlib
import typing

import pytest
import slack_sdk

import timesforge.storage

class Slack(slack_sdk.web.WebClient):

    def __init__(
        self,
        workspace: dict[str, typing.Any]
    ) -> None:

        super().__init__()

        self.workspace = workspace

    @typing.override
    def api_call(
        self,
        api_method: str,
        *,
        http_verb: str = 'POST',
        params: dict[str, typing.Any] | None = None,
        json: dict[str, typing.Any] | None = None,
        **_: object
    ) -> slack_sdk.web.SlackResponse:

        arguments = {key: value for key, value in {**(params or {}), **(json or {})}.items() if value is not None}

        match api_method:

            case 'users.list': data = page('members', self.workspace['users'], arguments)
            case 'conversations.list': data = page('channels', [channel for channel in self.workspace['channels'] if ('private_channel' if channel['is_private'] else 'public_channel') in arguments['types'].split(',')], arguments)
            case 'conversations.members': data = page('members', self.workspace['members'][arguments['channel']], arguments)
            case _: raise NotImplementedError(api_method)

        return slack_sdk.web.SlackResponse(client = self, http_verb = http_verb, api_url = api_method, req_args = {'params': arguments}, data = {'ok': True, **data}, headers = {}, status_code = 200).validate()

@pytest.fixture
def database(
    tmp_path: pathlib.Path
) -> collections.abc.Iterator[timesforge.storage.Database]:

    opening = timesforge.storage.Database(pathlib.Path(os.path.join(tmp_path, timesforge.storage.DATABASE_FILE))); yield opening
    opening.close()

@pytest.fixture
def workspace() -> dict[str, typing.Any]:

    directory = pathlib.Path(os.path.join(pathlib.Path(__file__).parent, 'fixtures', 'slack'))
    users, channels, members = (json.loads(pathlib.Path(os.path.join(directory, name)).read_text(encoding = 'utf-8')) for name in ('users.list.json', 'conversations.list.json', 'conversations.members.json'))

    return {'users': users, 'channels': channels, 'members': members}

@pytest.fixture
def slack(
    workspace: dict[str, typing.Any]
) -> Slack:

    return Slack(workspace)

def page(
    key: str,
    entries: list[typing.Any],
    arguments: dict[str, typing.Any]
) -> dict[str, typing.Any]:

    offset = int(arguments.get('cursor', 0))
    cursor = str(offset + 1) if offset + 1 < len(entries) else ''

    return {key: entries[offset:offset + 1], 'response_metadata': {'next_cursor': cursor}}
