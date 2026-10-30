"""Reconciliation of the times channels that TimesForge knows with their state in Slack."""

import collections.abc
import datetime
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.times.registry

def reconcile(
    client: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO,
    workspace_id: str,
    now: datetime.datetime,
    channel_ids: collections.abc.Collection[str] | None = None
) -> list[str]:

    """Brings the records of times channels in line with Slack.

    Slack tells the state of each times channel that is not deleted: a
    channel that Slack no longer has is marked as deleted, and one that was
    archived, restored or renamed in Slack is marked so. Whatever order Slack
    sent its events in, the records end up as Slack has the channels. The
    holders never change, and each change goes into the history.

    Args:
        client: Slack client with the bot token.
        registry: Times channels of the workspace.
        workspace_id: Slack workspace ID.
        now: The current time, which the changes take.
        channel_ids: Slack channel IDs of the channels to reconcile, or None for every one.

    Returns:
        Slack channel IDs of the channels whose records changed.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request for another reason than an unknown channel.
    """

    changes = []

    for channel in registry.scan(workspace_id):

        if channel_ids is not None and channel.channel_id not in channel_ids: continue
        if _reconcile(client, registry, workspace_id, channel, now): changes.append(channel.channel_id)

    return changes

def _reconcile(
    client: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO,
    workspace_id: str,
    channel: timesforge.times.registry.Channel,
    now: datetime.datetime
) -> bool:

    try:

        state: dict[str, typing.Any] = client.conversations_info(channel = channel.channel_id).get('channel', {})

    except slack_sdk.errors.SlackApiError as error:

        response: slack_sdk.web.SlackResponse = error.response

        if response.get('error') != 'channel_not_found': raise

        return registry.delete(workspace_id, channel.channel_id, now)

    changes = [registry.archive(workspace_id, channel.channel_id, now) if state.get('is_archived') else registry.unarchive(workspace_id, channel.channel_id, now), registry.rename(workspace_id, channel.channel_id, state.get('name', channel.channel_name), now)]

    return any(changes)
