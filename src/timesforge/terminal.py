"""Command-line entry point."""

import argparse
import contextlib
import datetime
import importlib.resources
import os
import pathlib
import sys

import slack_bolt.error
import slack_sdk.errors

import timesforge.configuration
import timesforge.product
import timesforge.slack.api
import timesforge.slack.application
import timesforge.slack.existing
import timesforge.slack.invitation
import timesforge.storage
import timesforge.times.registry

def main(
    arguments: list[str] | None = None
) -> int:

    """Runs the command.

    Args:
        arguments: Command-line arguments without the program name.
                   When None, the arguments of the current process are used.

    Returns:
        The exit status of the command.

    Raises:
        SystemExit: argparse handled the arguments itself:
                    it printed help or the version (status 0), or a usage error (status 2).
    """

    parser = _build()
    namespace = parser.parse_args(arguments)

    return namespace.handler(namespace)

def _build() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog = timesforge.product.COMMAND, description = timesforge.product.SUMMARY)
    parser.add_argument('--version', action = 'version', version = f'%(prog)s {timesforge.product.VERSION}')

    commands = parser.add_subparsers(title = 'commands', metavar = '<command>', required = True)
    importation = commands.add_parser('import', help = 'import times channels that members created by hand, with their holders')
    importation.set_defaults(handler = _import)
    importation.add_argument('--mapping', type = pathlib.Path, required = True, help = 'JSON file that maps channel IDs to the user IDs of their holders', metavar = 'FILE')
    mode = importation.add_mutually_exclusive_group(required = True)
    mode.add_argument('--dry-run', action = 'store_true', help = 'show what would be imported, changing nothing')
    mode.add_argument('--apply', action = 'store_true', help = 'import the channels, when every one of them can be')
    start = commands.add_parser('start', help = 'run the Slack app until it is stopped')
    start.set_defaults(handler = _start)
    manifest = commands.add_parser('manifest', help = 'print the manifest for creating the Slack app')
    manifest.set_defaults(handler = _manifest)
    doctor = commands.add_parser('doctor', help = 'check the settings, the Slack tokens, the database, the owner and the welcome channel')
    doctor.set_defaults(handler = _doctor)

    return parser

def _import(
    namespace: argparse.Namespace
) -> int:

    now = datetime.datetime.now(datetime.UTC)

    try:

        settings = timesforge.configuration.load()
        settings.require('slack_bot_token')

        mapping = timesforge.slack.existing.read(namespace.mapping)
        client = timesforge.slack.api.connect(settings.slack_bot_token)
        database = timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE)))

        try:

            workspace_id = client.auth_test().get('team_id', '')

            findings = timesforge.slack.existing.check(client, timesforge.times.registry.RegistryIO(database), workspace_id, mapping, now)
            errors = sum(finding.verdict == 'error' for finding in findings)

            for finding in findings: print(f'{finding.channel_id} {finding.holder_id}: {finding.verdict}' + (f' ({finding.reason})' if finding.reason else ''))

            count = timesforge.slack.existing.register(database, workspace_id, findings, now) if namespace.apply and not errors else 0

        finally:

            database.close()

    except (OSError, timesforge.configuration.ConfigurationError, timesforge.slack.existing.MappingInvalidError, timesforge.storage.DatabaseError, timesforge.times.registry.ChannelDuplicateError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    if namespace.apply: print(f'channels imported: {count}' if not errors else 'nothing imported, because some channels cannot be')

    return 1 if errors else 0

def _start(
    _: argparse.Namespace
) -> int:

    try:

        settings = timesforge.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'timesforge_owner_id', 'timesforge_channel_id_welcome')

        with contextlib.suppress(KeyboardInterrupt): timesforge.slack.application.serve(settings)

    except (timesforge.configuration.ConfigurationError, timesforge.slack.application.LockError, timesforge.storage.DatabaseError, slack_bolt.error.BoltError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    return 0

def _manifest(
    _: argparse.Namespace
) -> int:

    print(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'), end = '')

    return 0

def _doctor(
    _: argparse.Namespace
) -> int:

    try:

        settings = timesforge.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'timesforge_owner_id', 'timesforge_channel_id_welcome')

        print(f'ok: settings ({timesforge.configuration.locate()})')

        client = timesforge.slack.api.connect(settings.slack_bot_token)

        print(f"ok: Slack: {client.auth_test().get('url', '')}")

        client.apps_connections_open(app_token = settings.slack_app_token)

        print('ok: app-level token')

        if settings.slack_user_token:

            admin = timesforge.slack.api.connect(settings.slack_user_token).auth_test().get('user_id', '')

            if not client.users_info(user = admin).get('user', {}).get('is_admin'): raise timesforge.configuration.ConfigurationError('SLACK_USER_TOKEN must belong to an admin of the workspace')

            print(f'ok: user token: {admin}')

        timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE))).close()

        print('ok: database')

        if not timesforge.slack.invitation.eligible(client.users_info(user = settings.timesforge_owner_id).get('user', {})): raise timesforge.configuration.ConfigurationError('TIMESFORGE_OWNER_ID must be a member of the workspace')

        print(f'ok: owner: {settings.timesforge_owner_id}')

        channel = client.conversations_info(channel = settings.timesforge_channel_id_welcome).get('channel', {})

        if not channel.get('is_member'): raise timesforge.configuration.ConfigurationError(f"The bot must be in #{channel.get('name', '')} to welcome new members")

    except (timesforge.configuration.ConfigurationError, timesforge.storage.DatabaseError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    print(f"ok: welcome channel: #{channel.get('name', '')}")

    return 0
