"""Listeners of the Slack app, which answer the events and actions in the workspace."""

import typing

import slack_bolt

import timesforge.configuration
import timesforge.localisation
import timesforge.slack.permission
import timesforge.slack.view
import timesforge.storage
import timesforge.times.policy

def register(
    application: slack_bolt.App,
    settings: timesforge.configuration.Settings,
    database: timesforge.storage.Database
) -> None:

    """Registers the listeners of the app.

    The listeners call Slack with the client of the app, which holds the bot
    token of the one workspace, rather than with a client per request. What
    a view shows depends on the role of its viewer, and each view is in the
    language of the Slack locale of its viewer.

    Args:
        application: The application.
        settings: Settings of the deployment.
        database: Database with the times channels of each workspace.
    """

    def publish(
        event: dict[str, typing.Any],
        context: slack_bolt.BoltContext
    ) -> None:

        if event.get('tab') != 'home' or context.team_id is None: return

        refusal = timesforge.times.policy.decide(database.connect(), context.team_id, event['user'])
        user = application.client.users_info(user = event['user'], include_locale = True).get('user', {})
        language = timesforge.localisation.choose(user.get('locale'), settings.timesforge_language_display)
        application.client.views_publish(user_id = event['user'], view = timesforge.slack.view.home(refusal = refusal, role = timesforge.slack.permission.role(settings, event['user']), language = language))

    application.event('app_home_opened')(publish)
