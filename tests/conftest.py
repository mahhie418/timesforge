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
        workspace: dict[str, typing.Any],
        identity: str = 'UXXXB'
    ) -> None:

        super().__init__(token = 'xoxb-xxx', base_url = 'http://127.0.0.1:9/')

        self.workspace = workspace
        self.identity = identity

    @typing.override
    def api_call(
        self,
        api_method: str,
        *,
        params: dict[str, typing.Any] | None = None,
        json: dict[str, typing.Any] | None = None,
        **_: object
    ) -> slack_sdk.web.SlackResponse:

        arguments = {key: value for key, value in {**(params or {}), **(json or {})}.items() if value is not None}

        calls: list[tuple[str, dict[str, typing.Any]]] = self.workspace['calls']
        calls.append((api_method, arguments))

        match api_method:

            case 'auth.test': data = {'ok': True, 'team_id': 'TXXX', 'user_id': self.identity}
            case 'users.list': data = {'ok': True, **page('members', self.workspace['users'], arguments)}
            case 'users.info': data = next(({'ok': True, 'user': user} for user in self.workspace['users'] if user['id'] == arguments['user']), {'ok': False, 'error': 'user_not_found'})
            case 'conversations.info': data = next(({'ok': True, 'channel': channel} for channel in self.workspace['channels'] if channel['id'] == arguments['channel']), {'ok': False, 'error': 'channel_not_found'})
            case 'conversations.list': data = {'ok': True, **page('channels', [channel for channel in self.workspace['channels'] if ('private_channel' if channel['is_private'] else 'public_channel') in arguments['types'].split(',')], arguments)}
            case 'conversations.members': data = {'ok': True, **page('members', self.workspace['members'].get(arguments['channel'], []), arguments)}
            case 'conversations.create': return self.create(arguments)
            case 'conversations.invite': return self.invite(arguments)
            case 'views.open': data = {'ok': True, 'view': {'id': 'VXXX'}}
            case 'views.publish': data = {'ok': True}
            case _: raise NotImplementedError(api_method)

        return respond(self, api_method, arguments, data)

    def create(
        self,
        arguments: dict[str, typing.Any]
    ) -> slack_sdk.web.SlackResponse:

        failures: list[str | int] = self.workspace['failures']
        failure = failures.pop(0) if failures else None
        channels: list[dict[str, typing.Any]] = self.workspace['channels']

        if failure == 'dropped': raise TimeoutError('xxx')
        if isinstance(failure, int): return respond(self, 'conversations.create', arguments, {'ok': False, 'error': 'fatal_error'}, failure)
        if failure not in {None, 'lost'}: return respond(self, 'conversations.create', arguments, {'ok': False, 'error': failure})
        if any(channel['name'] == arguments['name'] for channel in channels): return respond(self, 'conversations.create', arguments, {'ok': False, 'error': 'name_taken'})

        channel = {'id': f'CXXX{len(channels) + 1}', 'name': arguments['name'], 'is_private': arguments['is_private'], 'is_archived': False, 'created': self.workspace['clock'], 'creator': self.identity}
        channels.append(channel)
        self.workspace['members'][channel['id']] = [self.identity]

        if failure == 'lost': raise TimeoutError('xxx')

        return respond(self, 'conversations.create', arguments, {'ok': True, 'channel': channel})

    def invite(
        self,
        arguments: dict[str, typing.Any]
    ) -> slack_sdk.web.SlackResponse:

        memberships: dict[str, list[str]] = self.workspace['members']
        refusals = self.workspace['refusals']
        requested: str = arguments['users']
        members = memberships.setdefault(arguments['channel'], [])
        users = requested.split(',')
        errors = [{'user': user, 'ok': False, 'error': refusals[user]} for user in users if user in refusals]

        members.extend(user for user in users if user not in refusals and user not in members)

        if errors: return respond(self, 'conversations.invite', arguments, {'ok': False, 'error': 'failed_for_some_users', 'errors': errors})

        return respond(self, 'conversations.invite', arguments, {'ok': True, 'channel': {'id': arguments['channel']}})

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

    return {'users': users, 'channels': channels, 'members': members, 'clock': 1793026800, 'failures': [], 'refusals': {}, 'calls': []}

@pytest.fixture
def slack(
    workspace: dict[str, typing.Any]
) -> Slack:

    return Slack(workspace)

@pytest.fixture
def writer(
    workspace: dict[str, typing.Any]
) -> Slack:

    return Slack(workspace, 'UXXX0')

def page(
    key: str,
    entries: list[typing.Any],
    arguments: dict[str, typing.Any]
) -> dict[str, typing.Any]:

    offset = int(arguments.get('cursor', 0))
    cursor = str(offset + 1) if offset + 1 < len(entries) else ''

    return {key: entries[offset:offset + 1], 'response_metadata': {'next_cursor': cursor}}

def respond(
    client: slack_sdk.web.WebClient,
    api_method: str,
    arguments: dict[str, typing.Any],
    data: dict[str, typing.Any],
    status: int = 200
) -> slack_sdk.web.SlackResponse:

    return slack_sdk.web.SlackResponse(client = client, http_verb = 'POST', api_url = api_method, req_args = {'params': arguments}, data = data, headers = {}, status_code = status).validate()
