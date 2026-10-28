"""Views of the Slack app: the App Home and its modals."""

import typing

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.permission
import timesforge.times.policy

def home(
    *,
    refusal: timesforge.times.policy.Refusal | None,
    role: timesforge.slack.permission.Role,
    language: timesforge.configuration.Language
) -> dict[str, typing.Any]:

    """Builds the App Home, which shows whether the viewer may create a times channel.

    The owner also sees their own role.

    Args:
        refusal: Why the viewer may not create a times channel, or None when they may.
        role: Role of the viewer.
        language: Language of the viewer.

    Returns:
        The view, as views.publish takes it.
    """

    fields = [(timesforge.localisation.translate('home.times', language), timesforge.localisation.translate(f'home.times.{refusal or 'available'}', language))]
    blocks = []

    if role != 'member': blocks.append({'type': 'context', 'elements': [{'type': 'mrkdwn', 'text': timesforge.localisation.translate(f'home.role.{role}', language)}]})

    blocks.append({'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f'*{title}*\n{text}'} for title, text in fields]})

    return {'type': 'home', 'blocks': blocks}
