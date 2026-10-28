"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import typing

import timesforge.configuration

type Role = typing.Literal['owner', 'member']

def role(
    settings: timesforge.configuration.Settings,
    user: str
) -> Role:

    """Tells the role of a Slack user.

    Args:
        settings: Settings of the deployment.
        user: Slack user ID.

    Returns:
        owner for the user in TIMESFORGE_OWNER_ID, or member for anyone else.
    """

    return 'owner' if user == settings.timesforge_owner_id else 'member'
