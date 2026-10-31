# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Roles of Slack users, which decide what each user sees and may do in the Slack app."""

import collections.abc
import typing

import slack_bolt

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

def restrict(
    settings: timesforge.configuration.Settings
) -> collections.abc.Callable[..., slack_bolt.BoltResponse | None]:

    """Builds a middleware that lets only the owner act.

    A request from anyone else, such as a pressed button, is acknowledged and
    dropped, so that no listener acts for them even if a view showed them a
    button.

    Args:
        settings: Settings of the deployment.

    Returns:
        The middleware, for the middleware of a listener.
    """

    def check(
        context: slack_bolt.BoltContext,
        ack: slack_bolt.Ack,
        next_: collections.abc.Callable[[], None]
    ) -> slack_bolt.BoltResponse | None:

        if context.user_id is None or role(settings, context.user_id) != 'owner': return ack()

        return next_()

    return check
