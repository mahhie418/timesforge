# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Views of the Slack app: the App Home, its modals and its messages."""

import datetime
import typing

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.permission
import timesforge.times.exclusion
import timesforge.times.history
import timesforge.times.naming
import timesforge.times.policy
import timesforge.times.recreation
import timesforge.times.registry
import timesforge.times.request

CREATION_ACTION = 'creation_action'
CREATION_CALLBACK = 'creation_callback'
EXCLUSION_ACTION = 'exclusion_action'
EXCLUSION_CALLBACK = 'exclusion_callback'
RECREATION_ACTION = 'recreation_action'
RECREATION_CALLBACK = 'recreation_callback'
RESOLUTION_ACTION = 'resolution_action'
RESOLUTION_CALLBACK = 'resolution_callback'
IMPORT_ACTION = 'import_action'
IMPORT_CALLBACK = 'import_callback'
HISTORY_ACTION = 'history_action'

NAME_INPUT = 'name_input'
MEMBER_INPUT = 'member_input'
CHANNEL_INPUT = 'channel_input'
CHOICE_INPUT = 'choice_input'
REASON_INPUT = 'reason_input'

def home(
    *,
    refusal: timesforge.times.policy.Refusal | None,
    eligible: bool,
    request: timesforge.times.request.Request | None,
    channels: list[timesforge.times.registry.Channel],
    exclusions: list[timesforge.times.exclusion.Exclusion],
    grants: list[timesforge.times.recreation.Grant],
    conflicts: list[timesforge.times.request.Request],
    role: timesforge.slack.permission.Role,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows whether the viewer may create a times channel.

    The App Home is published again whenever it is opened, so that it always
    shows the latest state. While the viewer may create a times channel, it
    tells what a times channel is, how it is named and that each member
    normally creates one, and a button at the right opens the modal that
    asks for their first name; a member whose channel was deleted sees that
    the owner let them create one more. While their request is approved,
    waits for the owner because its name is taken, or is being created, the
    App Home shows it instead, and after Slack refused to create its channel,
    it shows why next to the button. A member who is excluded, or whose
    channel was deleted without a recreation grant, sees so and no button.

    Below, the times channels that the viewer holds or held are listed with
    the day when each was created, archived or deleted, and each that is not
    deleted links to the channel. The owner also sees their own role and,
    under a heading, the requests that wait for them because their names are
    taken, each with a button that chooses another name, and the members
    excluded from creating times channels and those with recreation grants
    that are not used up, each with a button that changes them, a button
    that reviews the holders of the imported channels, and one that shows
    the history.

    Args:
        refusal: Why the viewer may not create a times channel, or None when the rules let them.
        eligible: Whether the viewer is a member of the workspace who may create times channels, rather than a guest.
        request: The latest request of the viewer, or None when they never asked.
        channels: Times channels that the viewer holds or held, oldest first.
        exclusions: Members excluded from creating times channels, which only the owner sees.
        grants: Recreation grants that are not used up, which only the owner sees.
        conflicts: Requests that wait for the owner because their names are taken, which only the owner sees.
        role: Role of the viewer.
        language: Language of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    match request:

        case timesforge.times.request.Request(status = 'reserved'): text, button = timesforge.localisation.translate('home.times.approved', language, channel = f'#{request.channel_name}'), None
        case timesforge.times.request.Request(status = 'pending_name_resolution'): text, button = timesforge.localisation.translate('home.times.pending', language, channel = f'#{request.channel_name}'), None
        case timesforge.times.request.Request(status = 'creating' | 'reconciling' | 'created' | 'inviting'): text, button = timesforge.localisation.translate('home.times.creating', language, channel = f'#{request.channel_name}'), None
        case _ if refusal is None and not eligible: text, button = timesforge.localisation.translate('home.times.ineligible', language), None
        case timesforge.times.request.Request(status = 'failed') if refusal is None: text, button = timesforge.localisation.translate('home.times.failed', language, channel = f'#{request.channel_name}', error = str(request.error)), _action(CREATION_ACTION, timesforge.localisation.translate('home.creation', language), style = 'primary')
        case _ if refusal is None: text, button = timesforge.localisation.translate('home.times.granted' if channels else 'home.times.available', language), _action(CREATION_ACTION, timesforge.localisation.translate('home.creation', language), style = 'primary')
        case _: text, button = timesforge.localisation.translate(f'home.times.{refusal}', language), None

    blocks = []

    if role != 'member': blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': timesforge.localisation.translate(f'home.role.{role}', language)}]})
    if button is not None: blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': timesforge.localisation.translate('home.prompt', language)}})

    blocks.append(_item(timesforge.localisation.translate('home.times', language), text, button))

    if channels: blocks.append(_item(timesforge.localisation.translate('home.channels', language), '\n'.join(_describe(channel, language) for channel in channels), None))

    if role == 'owner':

        blocks.extend([{'type': 'divider'}, _heading(timesforge.localisation.translate('home.heading.owner', language))])

        if not conflicts: blocks.append(_item(timesforge.localisation.translate('home.conflicts', language), timesforge.localisation.translate('home.conflicts.none', language), None))

        blocks.extend(_item(timesforge.localisation.translate('home.conflicts', language), timesforge.localisation.translate('home.conflict', language, user = f'<@{conflict.user_id}>', channel = f'#{conflict.channel_name}'), _action(RESOLUTION_ACTION, timesforge.localisation.translate('home.conflict.action', language), value = str(conflict.request_id))) for conflict in conflicts)

        blocks.append(_item(timesforge.localisation.translate('home.exclusions', language), ', '.join(f'<@{exclusion.user_id}>' for exclusion in exclusions) or timesforge.localisation.translate('home.exclusions.none', language), _action(EXCLUSION_ACTION, timesforge.localisation.translate('home.exclusions.action', language))))
        blocks.append(_item(timesforge.localisation.translate('home.recreations', language), ', '.join(f'<@{grant.user_id}>' for grant in grants) or timesforge.localisation.translate('home.recreations.none', language), _action(RECREATION_ACTION, timesforge.localisation.translate('home.recreations.action', language))))
        blocks.append(_item(timesforge.localisation.translate('home.imports', language), timesforge.localisation.translate('home.imports.text', language), _action(IMPORT_ACTION, timesforge.localisation.translate('home.imports.action', language))))
        blocks.append(_item(timesforge.localisation.translate('home.history', language), timesforge.localisation.translate('home.history.text', language), _action(HISTORY_ACTION, timesforge.localisation.translate('home.history.action', language))))

    return {'type': 'home', 'blocks': blocks}

def collect(
    *,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which a member enters the first name that names their times channel.

    Args:
        language: Language of the member.

    Returns:
        The view, as views.open takes it.
    """

    element = {'type': 'plain_text_input', 'action_id': NAME_INPUT, 'max_length': timesforge.times.naming.NAME_LENGTH_MAXIMUM - len(timesforge.times.naming.PREFIX)}
    block = {'type': 'input', 'block_id': NAME_INPUT, 'label': _plain(timesforge.localisation.translate('creation.name', language)), 'hint': _plain(timesforge.localisation.translate('creation.hint', language)), 'element': element}

    return {'type': 'modal', 'callback_id': CREATION_CALLBACK, 'title': _plain(timesforge.localisation.translate('creation.title', language)), 'submit': _plain(timesforge.localisation.translate('creation.submit', language)), 'close': _plain(timesforge.localisation.translate('creation.close', language)), 'blocks': [block]}

def approve(
    *,
    request: timesforge.times.request.Request,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that tells a member how their request was decided, once they submit their first name.

    Args:
        request: The open request of the member: approved, or pending while its name is taken.
        language: Language of the member.

    Returns:
        The view, as an update response takes it.
    """

    key = 'creation.pending' if request.status == 'pending_name_resolution' else 'creation.approval'

    return _modal(timesforge.localisation.translate('creation.title', language), timesforge.localisation.translate(key, language, channel = f'#{request.channel_name}'), language)

def report(
    *,
    request: timesforge.times.request.Request,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that tells a member how the creation of their times channel ended.

    Args:
        request: The request, once the creation ended: completed with a link
                 to the channel, failed, pending when Slack has a channel with
                 the name, or still open while nobody knows whether Slack
                 created the channel.
        language: Language of the member.

    Returns:
        The view, as views.update takes it.
    """

    channel = f'#{request.channel_name}'

    match request:

        case timesforge.times.request.Request(status = 'completed', channel_id = str() as channel_id): text = timesforge.localisation.translate('creation.success', language, channel = f'<#{channel_id}>')
        case timesforge.times.request.Request(status = 'failed'): text = timesforge.localisation.translate('creation.failure', language, channel = channel, error = str(request.error))
        case timesforge.times.request.Request(status = 'pending_name_resolution'): text = timesforge.localisation.translate('creation.pending', language, channel = channel)
        case _: text = timesforge.localisation.translate('creation.progress', language, channel = channel)

    return _modal(timesforge.localisation.translate('creation.title', language), text, language)

def exclude(
    *,
    exclusions: list[timesforge.times.exclusion.Exclusion],
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner excludes a member from creating times channels, or lets them create one again.

    The members excluded now are listed with the reasons, and excluding a
    member needs a reason.

    Args:
        exclusions: Members excluded now.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    lines = [timesforge.localisation.translate('exclusion.entry', language, user = f'<@{exclusion.user_id}>', reason = exclusion.reason) for exclusion in exclusions] or [timesforge.localisation.translate('exclusion.none', language)]
    choices = {choice: {'text': _plain(timesforge.localisation.translate(f'exclusion.choice.{choice}', language)), 'value': choice} for choice in ('exclude', 'include')}

    blocks = [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(lines)}},
        {'type': 'input', 'block_id': MEMBER_INPUT, 'label': _plain(timesforge.localisation.translate('exclusion.member', language)), 'element': {'type': 'users_select', 'action_id': MEMBER_INPUT}},
        {'type': 'input', 'block_id': CHOICE_INPUT, 'label': _plain(timesforge.localisation.translate('exclusion.choice', language)), 'element': {'type': 'radio_buttons', 'action_id': CHOICE_INPUT, 'options': list(choices.values()), 'initial_option': choices['exclude']}},
        {'type': 'input', 'block_id': REASON_INPUT, 'optional': True, 'label': _plain(timesforge.localisation.translate('exclusion.reason', language)), 'hint': _plain(timesforge.localisation.translate('exclusion.hint', language)), 'element': {'type': 'plain_text_input', 'action_id': REASON_INPUT}}
    ]

    return {'type': 'modal', 'callback_id': EXCLUSION_CALLBACK, 'title': _plain(timesforge.localisation.translate('exclusion.title', language)), 'submit': _plain(timesforge.localisation.translate('exclusion.submit', language)), 'close': _plain(timesforge.localisation.translate('exclusion.close', language)), 'blocks': blocks}

def grant(
    *,
    grants: list[timesforge.times.recreation.Grant],
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner gives a member a recreation grant, or revokes their unused one.

    The members with grants that are not used up are listed.

    Args:
        grants: Recreation grants that are not used up.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    users = ', '.join(f'<@{grant.user_id}>' for grant in grants) or timesforge.localisation.translate('recreation.none', language)
    choices = {choice: {'text': _plain(timesforge.localisation.translate(f'recreation.choice.{choice}', language)), 'value': choice} for choice in ('grant', 'revoke')}

    blocks = [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': f"{timesforge.localisation.translate('recreation.description', language)}\n{users}"}},
        {'type': 'input', 'block_id': MEMBER_INPUT, 'label': _plain(timesforge.localisation.translate('recreation.member', language)), 'element': {'type': 'users_select', 'action_id': MEMBER_INPUT}},
        {'type': 'input', 'block_id': CHOICE_INPUT, 'label': _plain(timesforge.localisation.translate('recreation.choice', language)), 'element': {'type': 'radio_buttons', 'action_id': CHOICE_INPUT, 'options': list(choices.values()), 'initial_option': choices['grant']}}
    ]

    return {'type': 'modal', 'callback_id': RECREATION_CALLBACK, 'title': _plain(timesforge.localisation.translate('recreation.title', language)), 'submit': _plain(timesforge.localisation.translate('recreation.submit', language)), 'close': _plain(timesforge.localisation.translate('recreation.close', language)), 'blocks': blocks}

def resolve(
    *,
    request: timesforge.times.request.Request,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner chooses another name for a request whose name is taken.

    The request travels with the view, so that submitting it names that request.

    Args:
        request: The request, which waits for the owner.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    element = {'type': 'plain_text_input', 'action_id': NAME_INPUT, 'max_length': timesforge.times.naming.NAME_LENGTH_MAXIMUM - len(timesforge.times.naming.PREFIX)}
    blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': timesforge.localisation.translate('resolution.description', language, user = f'<@{request.user_id}>', channel = f'#{request.channel_name}')}}, {'type': 'input', 'block_id': NAME_INPUT, 'label': _plain(timesforge.localisation.translate('resolution.name', language)), 'hint': _plain(timesforge.localisation.translate('resolution.hint', language)), 'element': element}]

    return {'type': 'modal', 'callback_id': RESOLUTION_CALLBACK, 'private_metadata': str(request.request_id), 'title': _plain(timesforge.localisation.translate('resolution.title', language)), 'submit': _plain(timesforge.localisation.translate('resolution.submit', language)), 'close': _plain(timesforge.localisation.translate('resolution.close', language)), 'blocks': blocks}

def review(
    *,
    channels: list[timesforge.times.registry.Channel],
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal in which the owner reviews the holders of the imported times channels, and changes one.

    Args:
        channels: The imported times channels that are not deleted.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    title = timesforge.localisation.translate('review.title', language)

    if not channels: return _modal(title, timesforge.localisation.translate('review.none', language), language)

    lines = [timesforge.localisation.translate('review.entry', language, channel = f'<#{channel.channel_id}>', user = f'<@{channel.holder_id}>') for channel in channels]
    options = [{'text': _plain(f'#{channel.channel_name}'), 'value': channel.channel_id} for channel in channels]

    blocks = [
        {'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(lines)}},
        {'type': 'input', 'block_id': CHANNEL_INPUT, 'label': _plain(timesforge.localisation.translate('review.channel', language)), 'element': {'type': 'static_select', 'action_id': CHANNEL_INPUT, 'options': options}},
        {'type': 'input', 'block_id': MEMBER_INPUT, 'label': _plain(timesforge.localisation.translate('review.member', language)), 'hint': _plain(timesforge.localisation.translate('review.hint', language)), 'element': {'type': 'users_select', 'action_id': MEMBER_INPUT}}
    ]

    return {'type': 'modal', 'callback_id': IMPORT_CALLBACK, 'title': _plain(title), 'submit': _plain(timesforge.localisation.translate('review.submit', language)), 'close': _plain(timesforge.localisation.translate('review.close', language)), 'blocks': blocks}

def trace(
    *,
    entries: list[timesforge.times.history.Entry],
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the modal that shows the owner the latest changes in the history, newest first.

    Args:
        entries: The changes, newest first.
        language: Language of the owner.

    Returns:
        The view, as views.open takes it.
    """

    title = timesforge.localisation.translate('history.title', language)

    if not entries: return _modal(title, timesforge.localisation.translate('history.none', language), language)

    unknown = timesforge.localisation.translate('history.unknown', language)
    blocks = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f"{_time(entry.creation)} {timesforge.localisation.translate(f'history.{entry.action}', language, actor = f'<@{entry.actor_id}>' if entry.actor_id else unknown, target = f'<@{entry.target_id}>', channel = f'<#{entry.channel_id}>', name = entry.details.get('channel_name', ''))}"}} for entry in entries]

    return {'type': 'modal', 'title': _plain(title), 'close': _plain(timesforge.localisation.translate('modal.close', language)), 'blocks': blocks}

def welcome(
    *,
    workspace: str,
    team_id: str,
    app_id: str,
    language: timesforge.configuration.Language
) -> tuple[str, list[dict[str, typing.Any]]]:

    """Builds the direct message that welcomes a new member and tells them how to create their times channel.

    It links to the App Home, where the member creates the channel.

    Args:
        workspace: Name of the workspace.
        team_id: Slack workspace ID.
        app_id: Slack app ID.
        language: Language of the member.

    Returns:
        The text of the message, for notifications, and its blocks, as chat.postMessage takes them.
    """

    title = timesforge.localisation.translate('welcome.title', language, workspace = workspace)
    body = timesforge.localisation.translate('welcome.body', language, workspace = workspace)
    link = f"<slack://app?team={team_id}&id={app_id}&tab=home|{timesforge.localisation.translate('welcome.action', language)}>"

    return f'{title}\n{body}', [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{title}*\n{body}'}}, {'type': 'section', 'text': {'type': 'mrkdwn', 'text': link}}]

def ready(
    *,
    channel_id: str,
    language: timesforge.configuration.Language
) -> tuple[str, list[dict[str, typing.Any]]]:

    """Builds the welcome message once the times channel of the member is created, with a link to the channel and no link to create one.

    Args:
        channel_id: Slack channel ID of the times channel.
        language: Language of the member.

    Returns:
        The text of the message, for notifications, and its blocks, as chat.update takes them.
    """

    title = timesforge.localisation.translate('ready.title', language)
    body = timesforge.localisation.translate('ready.body', language, channel = f'<#{channel_id}>')

    return f'{title}\n{body}', [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': f'*{title}*\n{body}'}}]

def _describe(
    channel: timesforge.times.registry.Channel,
    language: timesforge.configuration.Language
) -> str:

    match channel:

        case timesforge.times.registry.Channel(status = 'deleted', deletion = datetime.datetime() as moment): link, state = f'#{channel.channel_name}', timesforge.localisation.translate('home.channel.deleted', language, date = _date(moment))
        case timesforge.times.registry.Channel(status = 'archived', archival = datetime.datetime() as moment): link, state = f'<#{channel.channel_id}>', timesforge.localisation.translate('home.channel.archived', language, date = _date(moment))
        case _: link, state = f'<#{channel.channel_id}>', timesforge.localisation.translate('home.channel.active', language, date = _date(channel.creation))

    return timesforge.localisation.translate('home.channel', language, channel = link, state = state)

def _heading(
    text: str
) -> dict[str, typing.Any]:

    return {'type': 'header', 'text': _plain(text)}

def _item(
    title: str,
    text: str,
    accessory: dict[str, typing.Any] | None
) -> dict[str, typing.Any]:

    block = {'type': 'section', 'text': _text(title, text)}

    if accessory is not None: block['accessory'] = accessory

    return block

def _action(
    action: str,
    text: str,
    *,
    style: str | None = None,
    value: str | None = None
) -> dict[str, typing.Any]:

    button = {'type': 'button', 'action_id': action, 'text': _plain(text)}

    if style is not None: button['style'] = style
    if value is not None: button['value'] = value

    return button

def _date(
    moment: datetime.datetime
) -> str:

    return f'<!date^{int(moment.timestamp())}^{{date_short}}|{moment:%Y-%m-%d}>'

def _time(
    moment: datetime.datetime
) -> str:

    return f'<!date^{int(moment.timestamp())}^{{date_short}} {{time}}|{moment:%Y-%m-%d %H:%M} UTC>'

def _text(
    title: str,
    text: str
) -> dict[str, str]:

    return {'type': 'mrkdwn', 'text': f'*{title}*\n{text}'}

def _plain(
    text: str
) -> dict[str, str]:

    return {'type': 'plain_text', 'text': text}

def _modal(
    title: str,
    text: str,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    return {'type': 'modal', 'title': _plain(title), 'close': _plain(timesforge.localisation.translate('modal.close', language)), 'blocks': [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}]}
