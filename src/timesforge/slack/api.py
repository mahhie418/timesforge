# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Slack Web API calls, with pagination and retries."""

import collections.abc
import typing

import slack_sdk
import slack_sdk.http_retry

PAGE_SIZE = 200

RETRY_LIMIT = 5

def connect(
    token: str,
    *,
    idempotent: bool = True
) -> slack_sdk.web.WebClient:

    """Creates a client that sends a request again after a rate limit, a server error or a lost connection.

    A request is sent up to `RETRY_LIMIT` more times. After a rate limit,
    the client first waits as long as Slack asks. A request that must not
    take effect twice, such as one that creates a channel, needs a client
    that is not idempotent: it sends a request again only after a rate
    limit, before which Slack did nothing, because after a server error or a
    lost connection the request may have taken effect.

    Args:
        token: Slack bot token (xoxb-...) or user token (xoxp-...).
        idempotent: Whether the requests of the client may take effect twice.

    Returns:
        The client.
    """

    handlers: list[slack_sdk.http_retry.RetryHandler] = [slack_sdk.http_retry.builtin_handlers.RateLimitErrorRetryHandler(max_retry_count = RETRY_LIMIT)]

    if idempotent: handlers += [slack_sdk.http_retry.builtin_handlers.ServerErrorRetryHandler(max_retry_count = RETRY_LIMIT), slack_sdk.http_retry.builtin_handlers.ConnectionErrorRetryHandler(max_retry_count = RETRY_LIMIT)]

    return slack_sdk.web.WebClient(token = token, retry_handlers = handlers)

def users(
    client: slack_sdk.web.WebClient
) -> list[dict[str, typing.Any]]:

    """Fetches every user of the workspace, deactivated users and bots included.

    Args:
        client: Slack client for the workspace.

    Returns:
        The users, as users.list returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    return _paginate(client.users_list, 'members')

def channels(
    client: slack_sdk.web.WebClient
) -> list[dict[str, typing.Any]]:

    """Fetches the public channels of the workspace, archived ones included, except Slack Connect channels.

    A channel that is shared with another organisation, or waiting to be, is
    left out.

    Args:
        client: Slack client for the workspace.

    Returns:
        The channels, as conversations.list returns them.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    entries: list[dict[str, typing.Any]] = _paginate(client.conversations_list, 'channels', types = 'public_channel')

    return [entry for entry in entries if not (entry.get('is_ext_shared') or entry.get('is_pending_ext_shared'))]

def members(
    client: slack_sdk.web.WebClient,
    channel: str
) -> list[str]:

    """Fetches the members of a channel.

    Args:
        client: Slack client for the workspace.
        channel: ID of the channel.

    Returns:
        User IDs of the members.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request.
    """

    return _paginate(client.conversations_members, 'members', channel = channel)

def _paginate(
    method: collections.abc.Callable[..., slack_sdk.web.SlackResponse],
    key: str,
    **arguments: str | bool
) -> list[typing.Any]:

    entries = []
    cursor = None

    while True:

        response = method(cursor = cursor, limit = PAGE_SIZE, **arguments)
        page = response.get(key, [])
        metadata = response.get('response_metadata', {})

        entries.extend(page)

        if not (cursor := metadata.get('next_cursor')): return entries
