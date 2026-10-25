"""Times channels that members created by hand before timesforge, with the holders whom the owner confirmed."""

import collections
import collections.abc
import dataclasses
import datetime
import json
import pathlib
import re
import typing

import slack_sdk
import slack_sdk.errors

import timesforge.slack.invitation
import timesforge.storage
import timesforge.times.history
import timesforge.times.naming
import timesforge.times.registry

type Verdict = typing.Literal['import', 'skip', 'error']

_PATTERN_CHANNEL_ID = re.compile(r'C[A-Z0-9]{2,}')
_PATTERN_USER_ID = re.compile(r'[UW][A-Z0-9]{2,}')

class MappingInvalidError(ValueError):

    """Raised when a mapping file does not hold holder user IDs by channel ID."""

@dataclasses.dataclass(frozen = True, slots = True, kw_only = True)
class Finding:

    """What importing one channel does.

    Attributes:
        channel_id: Slack channel ID.
        holder_id: Slack user ID of the holder.
        verdict: import when the channel can be imported, skip when timesforge has it with the same holder, or error when it cannot be imported.
        reason: Why the channel is skipped or cannot be imported, as a Slack error code or one of registered, private, name, holder, held and duplicate; None when it can be imported.
        channel: The channel to register, or None when it is not imported.
    """

    channel_id: str
    holder_id: str
    verdict: Verdict
    reason: str | None = None
    channel: timesforge.times.registry.Channel | None = None

def read(
    file: pathlib.Path
) -> dict[str, str]:

    """Reads a mapping of times channels to their holders.

    Args:
        file: JSON file with one object, whose keys are Slack channel IDs and whose values are Slack user IDs.

    Returns:
        Holder user IDs by channel ID.

    Raises:
        MappingInvalidError: The file cannot be read, or it holds something else.
        OSError: The file cannot be opened.
    """

    try: entries = json.loads(file.read_text(encoding = 'utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise MappingInvalidError(f'{file} is not a JSON file: {error}') from None

    if not isinstance(entries, dict): raise MappingInvalidError(f'{file} must hold one JSON object')

    if (invalid := sorted(str(channel) for channel, holder in entries.items() if not (isinstance(channel, str) and _PATTERN_CHANNEL_ID.fullmatch(channel) and isinstance(holder, str) and _PATTERN_USER_ID.fullmatch(holder)))): raise MappingInvalidError(f'{file} must map Slack channel IDs to Slack user IDs: {', '.join(invalid)}')

    return entries

def check(
    client: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO,
    workspace_id: str,
    mapping: collections.abc.Mapping[str, str],
    now: datetime.datetime
) -> list[Finding]:

    """Checks a mapping of existing times channels to their holders, changing nothing.

    Slack must have each channel as a public channel named after a first name,
    and its holder must be a member who is invited to times channels. The
    holder of a channel is whom the mapping names, whoever Slack records as
    its creator. timesforge must not have the channel with another holder,
    nor the holder with another times channel that is not deleted, and the
    mapping must not name a holder twice.

    Args:
        client: Slack client with the bot token.
        registry: Times channels of the workspace.
        workspace_id: Slack workspace ID.
        mapping: Holder user IDs by channel ID.
        now: The current time, which archived channels take as their archival.

    Returns:
        One finding for each channel, in the order of the mapping.

    Raises:
        slack_sdk.errors.SlackApiError: Slack refused a request for another reason than an unknown channel or user.
    """

    counts = collections.Counter(mapping.values())

    return [_check(client, registry, workspace_id, (channel_id, holder_id), now) if counts[holder_id] == 1 else Finding(channel_id = channel_id, holder_id = holder_id, verdict = 'error', reason = 'duplicate') for channel_id, holder_id in mapping.items()]

def register(
    database: timesforge.storage.Database,
    workspace_id: str,
    findings: collections.abc.Iterable[Finding],
    now: datetime.datetime
) -> int:

    """Registers the channels that can be imported, in one transaction.

    Args:
        database: The database that holds the times channels.
        workspace_id: Slack workspace ID.
        findings: Findings of `check`.
        now: The current time.

    Returns:
        Number of channels registered.

    Raises:
        timesforge.times.registry.ChannelDuplicateError: A channel or its holder
                                                         was registered since the check.
    """

    channels = [finding.channel for finding in findings if finding.verdict == 'import' and finding.channel is not None]

    with database.begin() as connection:

        for channel in channels:

            timesforge.times.registry.insert(connection, workspace_id, channel)
            timesforge.times.history.record(connection, workspace_id, timesforge.times.history.Entry(action = 'import', target_id = channel.holder_id, channel_id = channel.channel_id, creation = now))

    return len(channels)

def _check(
    client: slack_sdk.web.WebClient,
    registry: timesforge.times.registry.RegistryIO,
    workspace_id: str,
    entry: tuple[str, str],
    now: datetime.datetime
) -> Finding:

    channel_id, holder_id = entry

    def refuse(
        reason: str
    ) -> Finding:

        return Finding(channel_id = channel_id, holder_id = holder_id, verdict = 'error', reason = reason)

    try:

        channel: dict[str, typing.Any] = client.conversations_info(channel = channel_id).get('channel', {})
        user: dict[str, typing.Any] = client.users_info(user = holder_id).get('user', {})

    except slack_sdk.errors.SlackApiError as error:

        response: slack_sdk.web.SlackResponse = error.response

        if response.get('error') in {'channel_not_found', 'user_not_found'}: return refuse(str(response.get('error')))

        raise

    name = channel.get('name', '')
    first_name = name.removeprefix(timesforge.times.naming.PREFIX)

    if channel.get('is_private'): return refuse('private')
    if not name.startswith(timesforge.times.naming.PREFIX) or _sanitise(first_name) != name: return refuse('name')
    if not timesforge.slack.invitation.eligible(user): return refuse('holder')

    if (known := registry.load(workspace_id, channel_id)) is not None: return Finding(channel_id = channel_id, holder_id = holder_id, verdict = 'skip', reason = 'registered') if known.holder_id == holder_id else refuse('registered')
    if any(held.status != 'deleted' for held in registry.find(workspace_id, holder_id)): return refuse('held')

    archived = bool(channel.get('is_archived'))
    registration = timesforge.times.registry.Channel(channel_id = channel_id, holder_id = holder_id, first_name = first_name, channel_name = name, source = 'imported', status = 'archived' if archived else 'active', creation = datetime.datetime.fromtimestamp(channel['created'], datetime.UTC), archival = now if archived else None)

    return Finding(channel_id = channel_id, holder_id = holder_id, verdict = 'import', channel = registration)

def _sanitise(
    first_name: str
) -> str | None:

    try: return timesforge.times.naming.sanitise(first_name)
    except timesforge.times.naming.NameInvalidError: return None
