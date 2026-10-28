"""Slack app of the workspace, connected to Slack through Socket Mode."""

import collections.abc
import contextlib
import os
import pathlib
import sqlite3

import slack_bolt
import slack_bolt.adapter.socket_mode
import slack_sdk

import timesforge.configuration
import timesforge.product
import timesforge.slack.api
import timesforge.slack.handler
import timesforge.storage

LOCK_FILE = 'serve.lock'

class LockError(Exception):

    """Raised when another app already serves with the same data directory."""

def build(
    client: slack_sdk.web.WebClient,
    settings: timesforge.configuration.Settings,
    database: timesforge.storage.Database
) -> slack_bolt.App:

    """Builds the Slack app with its listeners.

    Args:
        client: Slack client with the bot token.
        settings: Settings of the deployment.
        database: Database with the times channels of each workspace.

    Returns:
        The app.

    Raises:
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    application = slack_bolt.App(token = client.token, client = client)
    timesforge.slack.handler.register(application, settings, database)

    return application

@contextlib.contextmanager
def lock(
    directory: pathlib.Path
) -> collections.abc.Generator[None]:

    """Holds the lock file in the data directory while the app serves.

    A second Socket Mode connection would split the events and the button
    presses between two apps, so only one app may serve with a data
    directory. The lock file is a SQLite database held in an exclusive
    transaction, which works alike on every operating system, and the lock
    goes when the process ends, even when it crashes.

    Args:
        directory: Data directory of the app, created when missing.

    Yields:
        Nothing; the lock is held until the block ends.

    Raises:
        LockError: Another app holds the lock.
    """

    directory.mkdir(parents = True, exist_ok = True)

    connection = sqlite3.connect(pathlib.Path(os.path.join(directory, LOCK_FILE)), timeout = 0, autocommit = True)

    try:

        try: connection.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError: raise LockError(f'{timesforge.product.NAME} is already running with the data directory {directory}') from None
        yield

    finally:

        connection.close()

def serve(
    settings: timesforge.configuration.Settings
) -> None:

    """Serves the Slack app until the process stops.

    Args:
        settings: Settings of the deployment, with the bot and app-level tokens.

    Raises:
        LockError: Another app already serves with the data directory.
        timesforge.storage.DatabaseError: The database cannot be used.
        slack_bolt.error.BoltError: Slack refused the bot token.
    """

    with lock(settings.timesforge_data_directory):

        database = timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE)))

        try: start(build(timesforge.slack.api.connect(settings.slack_bot_token), settings, database), settings.slack_app_token)
        finally: database.close()

def start(
    application: slack_bolt.App,
    token: str
) -> None:

    """Connects the app to Slack through Socket Mode and serves it until the process stops.

    Args:
        application: The application.
        token: App-level token of the Slack app (xapp-...).
    """

    slack_bolt.adapter.socket_mode.SocketModeHandler(application, token).start()
