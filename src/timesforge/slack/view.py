"""Views of the Slack app: the App Home and its modals."""

import datetime
import typing

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.permission
import timesforge.times.exclusion
import timesforge.times.naming
import timesforge.times.policy
import timesforge.times.registry
import timesforge.times.request

CREATION_ACTION = 'creation_action'
CREATION_CALLBACK = 'creation_callback'
EXCLUSION_ACTION = 'exclusion_action'
EXCLUSION_CALLBACK = 'exclusion_callback'

NAME_INPUT = 'name_input'
MEMBER_INPUT = 'member_input'
CHOICE_INPUT = 'choice_input'
REASON_INPUT = 'reason_input'

def home(
    *,
    refusal: timesforge.times.policy.Refusal | None,
    eligible: bool,
    request: timesforge.times.request.Request | None,
    channels: list[timesforge.times.registry.Channel],
    exclusions: list[timesforge.times.exclusion.Exclusion],
    role: timesforge.slack.permission.Role,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows whether the viewer may create a times channel.

    While the viewer may, a button at the right opens the modal that asks for
    their first name. While their request is approved, waits for the owner
    because its name is taken, or is being created, the App Home shows it
    instead, and after Slack refused to create its channel, it shows why next
    to the button. Below, the times channels that the viewer holds or held
    are listed with the day when each was created, archived or deleted, and
    each that is not deleted links to the channel. The owner also sees their
    own role and, under a heading, the members excluded from creating times
    channels, with a button that changes them.

    Args:
        refusal: Why the viewer may not create a times channel, or None when the rules let them.
        eligible: Whether the viewer is a member of the workspace who may create times channels, rather than a guest.
        request: The latest request of the viewer, or None when they never asked.
        channels: Times channels that the viewer holds or held, oldest first.
        exclusions: Members excluded from creating times channels, which only the owner sees.
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
        case _ if refusal is None: text, button = timesforge.localisation.translate('home.times.available', language), _action(CREATION_ACTION, timesforge.localisation.translate('home.creation', language), style = 'primary')
        case _: text, button = timesforge.localisation.translate(f'home.times.{refusal}', language), None

    blocks = []

    if role != 'member': blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': timesforge.localisation.translate(f'home.role.{role}', language)}]})

    blocks.append(_item(timesforge.localisation.translate('home.times', language), text, button))

    if channels: blocks.append(_item(timesforge.localisation.translate('home.channels', language), '\n'.join(_describe(channel, language) for channel in channels), None))

    if role == 'owner':

        blocks.extend([{'type': 'divider'}, _heading(timesforge.localisation.translate('home.heading.owner', language))])
        blocks.append(_item(timesforge.localisation.translate('home.exclusions', language), ', '.join(f'<@{exclusion.user_id}>' for exclusion in exclusions) or timesforge.localisation.translate('home.exclusions.none', language), _action(EXCLUSION_ACTION, timesforge.localisation.translate('home.exclusions.action', language))))

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
    style: str | None = None
) -> dict[str, typing.Any]:

    button = {'type': 'button', 'action_id': action, 'text': _plain(text)}

    if style is not None: button['style'] = style

    return button

def _date(
    moment: datetime.datetime
) -> str:

    return f'<!date^{int(moment.timestamp())}^{{date_short}}|{moment:%Y-%m-%d}>'

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
