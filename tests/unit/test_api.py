import typing

import slack_sdk
import slack_sdk.http_retry

import timesforge.slack.api

HANDLERS = (slack_sdk.http_retry.builtin_handlers.RateLimitErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ServerErrorRetryHandler, slack_sdk.http_retry.builtin_handlers.ConnectionErrorRetryHandler)

def test_api_client_retry() -> None:

    client = timesforge.slack.api.connect('xoxb-xxx')

    assert {type(handler): handler.max_retry_count for handler in client.retry_handlers} == dict.fromkeys(HANDLERS, timesforge.slack.api.RETRY_LIMIT)

def test_api_users_pagination(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    assert timesforge.slack.api.users(slack) == workspace['users']

def test_api_channels_exclusion(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    channels = list(workspace['channels'])
    workspace['channels'] += [channels[0] | {'id': 'CXXX3', 'is_private': True}, channels[0] | {'id': 'CXXX4', 'is_ext_shared': True}, channels[0] | {'id': 'CXXX5', 'is_pending_ext_shared': True}]

    assert timesforge.slack.api.channels(slack) == channels

def test_api_members_pagination(
    workspace: dict[str, typing.Any],
    slack: slack_sdk.web.WebClient
) -> None:

    assert timesforge.slack.api.members(slack, 'CXXX1') == workspace['members']['CXXX1']
