"""Views of the Slack app: the App Home and its modals."""

import typing

import timesforge.slack.permission
import timesforge.times.policy

_STATES = {None: 'You can create one.', 'holder': 'You have one.', 'used': 'Yours was deleted.', 'excluded': 'You cannot create one.'}

def home(
    *,
    refusal: timesforge.times.policy.Refusal | None,
    role: timesforge.slack.permission.Role
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows whether the viewer may create a times channel.

    The owner also sees their own role.

    Args:
        refusal: Why the viewer may not create a times channel, or None when they may.
        role: Role of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    fields = [('times channel', _STATES[refusal])]
    blocks = []

    if role != 'member': blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': 'You are the owner.'}]})

    blocks.append({'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'*{title}*\n{text}'} for title, text in fields]})

    return {'type': 'home', 'blocks': blocks}
