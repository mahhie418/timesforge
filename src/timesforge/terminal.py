"""Command-line entry point."""

import argparse
import contextlib
import datetime
import getpass
import importlib.resources
import json
import os
import pathlib
import sys
import urllib.parse
import webbrowser

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
    setup = commands.add_parser('setup', help = 'create the Slack app and choose the owner, writing the settings file')
    setup.set_defaults(handler = _setup)

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

        if settings.slack_user_token: print(f'ok: user token: {_authorise(client, settings.slack_user_token)}')

        timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE))).close()

        print('ok: database')

        print(f'ok: owner: {_name(client, settings.timesforge_owner_id)}')

        channel = client.conversations_info(channel = settings.timesforge_channel_id_welcome).get('channel', {})

        if not channel.get('is_member'): raise timesforge.configuration.ConfigurationError(f"The bot must be in #{channel.get('name', '')} to welcome new members")

    except (timesforge.configuration.ConfigurationError, timesforge.storage.DatabaseError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    print(f"ok: welcome channel: #{channel.get('name', '')}")

    return 0

def _setup(
    _: argparse.Namespace
) -> int:

    try:

        _create(); _appoint()

    except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error:

        print(f'error: {error}', file = sys.stderr)

        return 1

    except (EOFError, KeyboardInterrupt):

        print('\nerror: Setup was stopped', file = sys.stderr)

        return 1

    return 0

def _create() -> None:

    settings = timesforge.configuration.load()
    manifest = json.loads(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))

    url = f'https://api.slack.com/apps?new_app=1&manifest_json={urllib.parse.quote(json.dumps(manifest, separators = (',', ':')))}'

    print(f'Create the Slack app from its manifest: {url}')
    print('Choose the workspace, create the app and install it. Then copy the Bot User OAuth Token in OAuth & Permissions, and generate an App-Level Token with the connections:write scope in Basic Information. Where only admins may create public channels, an admin installs the app, and the User OAuth Token in OAuth & Permissions is copied too.', flush = True)

    webbrowser.open(url)

    while True:

        bot, app, user = _ask('Bot User OAuth Token', settings.slack_bot_token, secret = True), _ask('App-Level Token', settings.slack_app_token, secret = True), _ask('User OAuth Token, or nothing where members may create public channels', settings.slack_user_token, secret = True)

        try: identity = _identify(bot, app, user)
        except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: print(f'error: {error}', file = sys.stderr)
        else: break

    timesforge.configuration.save({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app, 'SLACK_USER_TOKEN': user})

    print(f"ok: Slack: {identity.get('url', '')}")

def _identify(
    bot: str,
    app: str,
    user: str
) -> slack_sdk.web.SlackResponse:

    timesforge.configuration.load({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app, 'SLACK_USER_TOKEN': user}).require('slack_bot_token', 'slack_app_token')
    client = timesforge.slack.api.connect(bot)
    identity = client.auth_test()
    client.apps_connections_open(app_token = app)

    if user: _authorise(client, user)

    return identity

def _authorise(
    client: slack_sdk.web.WebClient,
    token: str
) -> str:

    admin = timesforge.slack.api.connect(token).auth_test().get('user_id', '')

    if not client.users_info(user = admin).get('user', {}).get('is_admin'): raise timesforge.configuration.ConfigurationError('SLACK_USER_TOKEN must belong to an admin of the workspace')

    return admin

def _appoint() -> None:

    settings = timesforge.configuration.load()
    client = timesforge.slack.api.connect(settings.slack_bot_token)

    print('Copy the member ID of the owner in Slack: open the profile, choose the ⋮ button and Copy member ID.', flush = True)

    while True:

        owner = _ask('Member ID of the owner', settings.timesforge_owner_id, secret = False)

        try: name = _name(client, owner)
        except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: print(f'error: {error}', file = sys.stderr)
        else: break

    timesforge.configuration.save({'TIMESFORGE_OWNER_ID': owner})

    print(f'ok: owner: {name}')

def _name(
    client: slack_sdk.web.WebClient,
    user: str
) -> str:

    timesforge.configuration.load({'TIMESFORGE_OWNER_ID': user}).require('timesforge_owner_id')
    entry = client.users_info(user = user).get('user', {})

    if not timesforge.slack.invitation.eligible(entry): raise timesforge.configuration.ConfigurationError(f'{user} is not a member of the workspace')

    profile = entry.get('profile', {})

    return profile.get('display_name') or profile.get('real_name') or entry.get('name') or user

def _ask(
    question: str,
    current: str,
    *,
    secret: bool
) -> str:

    hint = (' [keep current]' if secret else f' [{current}]') if current else ''
    answer = (getpass.getpass if secret else input)(f'{question}{hint}: ')

    return answer.strip() or current
