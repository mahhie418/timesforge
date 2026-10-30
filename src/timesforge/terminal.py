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
import typing
import urllib.parse

import rich.console
import rich.style
import rich.text
import slack_bolt.error
import slack_sdk.errors

import timesforge.autostart
import timesforge.configuration
import timesforge.product
import timesforge.shortener
import timesforge.slack.api
import timesforge.slack.application
import timesforge.slack.existing
import timesforge.slack.invitation
import timesforge.storage
import timesforge.times.naming
import timesforge.times.registry

_STATUS_STYLES = {'OK': 'bold green', 'NEXT': 'bold cyan', 'WARNING': 'bold yellow', 'ERROR': 'bold red'}

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
    start.add_argument('--log', type = pathlib.Path, help = 'file to append the output to', metavar = 'FILE')
    stop = commands.add_parser('stop', help = 'stop the Slack app and stop it from starting at login')
    stop.set_defaults(handler = _stop)
    manifest = commands.add_parser('manifest', help = 'print the manifest for creating the Slack app')
    manifest.set_defaults(handler = _manifest)
    doctor = commands.add_parser('doctor', help = 'check the settings, the Slack tokens, the database, the owner and the welcome channel')
    doctor.set_defaults(handler = _doctor)
    setup = commands.add_parser('setup', help = 'create the Slack app, choose the owner and the welcome channel and start the Slack app at login, writing the settings file')
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

        _report('ERROR', str(error))

        return 1

    if namespace.apply: print(f'channels imported: {count}' if not errors else 'nothing imported, because some channels cannot be')

    return 1 if errors else 0

def _start(
    namespace: argparse.Namespace
) -> int:

    log: pathlib.Path | None = namespace.log

    if log is None: return _serve()

    log.parent.mkdir(parents = True, exist_ok = True)

    with log.open('a', encoding = 'utf-8', buffering = 1) as file, contextlib.redirect_stdout(file), contextlib.redirect_stderr(file): return _serve()

def _serve() -> int:

    try:

        settings = timesforge.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'timesforge_owner_id', 'timesforge_channel_id_welcome')

        with contextlib.suppress(KeyboardInterrupt): timesforge.slack.application.serve(settings)

    except (timesforge.configuration.ConfigurationError, timesforge.slack.application.LockError, timesforge.storage.DatabaseError, slack_bolt.error.BoltError) as error:

        _report('ERROR', str(error))

        return 1

    return 0

def _stop(
    _: argparse.Namespace
) -> int:

    try:

        registration = timesforge.autostart.unregister(pathlib.Path(os.path.join(timesforge.configuration.load().timesforge_data_directory, 'start.log')))

    except (timesforge.configuration.ConfigurationError, timesforge.autostart.AutostartError) as error:

        _report('ERROR', str(error))

        return 1

    _report('OK', f'autostart: removed {registration}' if registration else 'autostart: not registered')

    return 0

def _manifest(
    _: argparse.Namespace
) -> int:

    print(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'), end = '')

    return 0

def _doctor(
    _: argparse.Namespace
) -> int:

    return _check(guided = False)

def _check(
    *,
    guided: bool
) -> int:

    try:

        settings = timesforge.configuration.load()
        settings.require('slack_bot_token', 'slack_app_token', 'timesforge_owner_id', 'timesforge_channel_id_welcome')

        _report('OK', f'settings ({timesforge.configuration.locate()})')

        client = timesforge.slack.api.connect(settings.slack_bot_token)

        _report('OK', f"Slack: {client.auth_test().get('url', '')}")

        client.apps_connections_open(app_token = settings.slack_app_token)

        _report('OK', 'app-level token')

        if settings.slack_user_token: _report('OK', f'user token: {_authorise(client, settings.slack_user_token)}')

        timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE))).close()

        _report('OK', 'database')

        _report('OK', f'owner: {_name(client, settings.timesforge_owner_id)}')

        name = _inspect(client, settings.timesforge_channel_id_welcome)
        channels = _find(client, settings) if guided else []

    except (timesforge.configuration.ConfigurationError, timesforge.storage.DatabaseError, slack_sdk.errors.SlackApiError) as error:

        _report('ERROR', str(error))

        return 1

    _report('OK', f'welcome channel: #{name}')

    if channels: _report('NEXT', f"import the times channels that members created by hand with '{timesforge.product.COMMAND} import --mapping FILE': {', '.join(f'#{channel.get('name', '')} ({channel.get('id', '')})' for channel in channels)}")

    return 0

def _find(
    client: slack_sdk.web.WebClient,
    settings: timesforge.configuration.Settings
) -> list[dict[str, typing.Any]]:

    workspace_id = client.auth_test().get('team_id', '')
    database = timesforge.storage.Database(pathlib.Path(os.path.join(settings.timesforge_data_directory, timesforge.storage.DATABASE_FILE)))

    try:

        registry = timesforge.times.registry.RegistryIO(database)

        return [channel for channel in timesforge.slack.api.channels(client) if channel.get('name', '').startswith(timesforge.times.naming.PREFIX) and registry.load(workspace_id, channel.get('id', '')) is None]

    finally:

        database.close()

def _setup(
    _: argparse.Namespace
) -> int:

    print()
    _console().print(rich.text.Text.assemble(('TimesForge', 'bold'), ' ', (f'(Version: {timesforge.product.VERSION})', 'dim')))

    try:

        with timesforge.shortener.Shortener() as shortener:

            if shortener.failure is not None: _report('WARNING', f'Short links are not available on this computer ({shortener.failure}), so the full address follows', blank = True)

            _create(shortener); _appoint(); _welcome()

        print()

        if (status := _check(guided = True)) == 0: _autostart()

    except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError, timesforge.autostart.AutostartError) as error:

        _report('ERROR', str(error), blank = True)

        return 1

    except (EOFError, KeyboardInterrupt):

        print(file = sys.stderr)
        _report('ERROR', 'Setup was stopped', blank = True)

        return 1

    finally:

        print()

    return status

def _create(
    shortener: timesforge.shortener.Shortener
) -> None:

    settings = timesforge.configuration.load()
    manifest = json.loads(importlib.resources.files('timesforge.slack').joinpath('manifest.json').read_text(encoding = 'utf-8'))

    url = f'https://api.slack.com/apps?new_app=1&manifest_json={urllib.parse.quote(json.dumps(manifest, separators = (',', ':')))}'

    print('\nOpen the link below to create the Slack app. Its settings are filled in from the manifest.')
    _link(shortener.shorten('slack', url))
    _steps('Choose the workspace, then follow the pages to create the app.', 'Choose Install to Workspace and allow the access the app asks for. Where only admins may create public channels, an admin does this.', 'In OAuth & Permissions, copy the Bot User OAuth Token (it starts with xoxb-), and the User OAuth Token (it starts with xoxp-) where only admins may create public channels.', 'In Basic Information, under App-Level Tokens, generate a token with the connections:write scope and copy it (it starts with xapp-).')

    while True:

        print('\nPaste the Bot User OAuth Token and the App-Level Token, and the User OAuth Token where only admins may create public channels. They stay hidden as you type.\n', flush = True)
        bot, app, user = _ask('Bot User OAuth Token', settings.slack_bot_token, secret = True), _ask('App-Level Token', settings.slack_app_token, secret = True), _ask('User OAuth Token', settings.slack_user_token, secret = True)

        try: identity = _identify(bot, app, user)
        except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: _report('ERROR', str(error), blank = True)
        else: break

    timesforge.configuration.save({'SLACK_BOT_TOKEN': bot, 'SLACK_APP_TOKEN': app, 'SLACK_USER_TOKEN': user})

    _report('OK', f"Slack: {identity.get('url', '')}", blank = True)

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

    print('\nChoose who owns TimesForge in Slack, and copy their member ID.')
    _steps('In Slack, open their profile.', 'Choose ⋮ (More), then Copy member ID.')

    while True:

        print()
        owner = _ask('Member ID of the owner', settings.timesforge_owner_id, secret = False)

        try: name = _name(client, owner)
        except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: _report('ERROR', str(error), blank = True)
        else: break

    timesforge.configuration.save({'TIMESFORGE_OWNER_ID': owner})

    _report('OK', f'owner: {name}', blank = True)

def _name(
    client: slack_sdk.web.WebClient,
    user: str
) -> str:

    timesforge.configuration.load({'TIMESFORGE_OWNER_ID': user}).require('timesforge_owner_id')
    entry = client.users_info(user = user).get('user', {})

    if not timesforge.slack.invitation.eligible(entry): raise timesforge.configuration.ConfigurationError(f'{user} is not a member of the workspace')

    profile = entry.get('profile', {})

    return profile.get('display_name') or profile.get('real_name') or entry.get('name') or user

def _welcome() -> None:

    settings = timesforge.configuration.load()
    client = timesforge.slack.api.connect(settings.slack_bot_token)
    channel = settings.timesforge_channel_id_welcome

    print('\nChoose the channel that new members join, such as #welcome, and copy its channel ID.')
    _steps('In Slack, open the channel and choose its name at the top.', 'At the bottom of About, copy the channel ID.', 'In the channel, send /invite @TimesForge so that the bot joins it.')

    while True:

        print()
        channel = _ask('Channel ID of the welcome channel', channel, secret = False)

        try: _inspect(client, channel)
        except (timesforge.configuration.ConfigurationError, slack_sdk.errors.SlackApiError) as error: _report('ERROR', str(error), blank = True)
        else: break

    timesforge.configuration.save({'TIMESFORGE_CHANNEL_ID_WELCOME': channel})

def _inspect(
    client: slack_sdk.web.WebClient,
    channel: str
) -> str:

    timesforge.configuration.load({'TIMESFORGE_CHANNEL_ID_WELCOME': channel}).require('timesforge_channel_id_welcome')
    entry = client.conversations_info(channel = channel).get('channel', {})

    if not entry.get('is_member'): raise timesforge.configuration.ConfigurationError(f"The bot must be in #{entry.get('name', '')} to welcome new members")

    return entry.get('name', '')

def _autostart() -> None:

    if sys.platform in timesforge.autostart.PLATFORMS: print()

    log = pathlib.Path(os.path.join(timesforge.configuration.load().timesforge_data_directory, 'start.log'))

    if sys.platform not in timesforge.autostart.PLATFORMS or not _agree('Start the Slack app automatically when you log in?', default = True):

        registration = timesforge.autostart.unregister(log) if sys.platform in timesforge.autostart.PLATFORMS else None

        if registration: _report('OK', f'autostart: removed {registration}', blank = True)

        _report('NEXT', f"run '{timesforge.product.COMMAND} start' to start the Slack app", blank = not registration)

        return

    _report('OK', f'autostart: {timesforge.autostart.register(log)}', blank = True)

def _ask(
    question: str,
    current: str,
    *,
    secret: bool
) -> str:

    hint = (' [keep current]' if secret else f' [{current}]') if current else ''
    answer = (getpass.getpass if secret else input)(f'{question}{hint}: ')

    return answer.strip() or current

def _agree(
    question: str,
    *,
    default: bool
) -> bool:

    hint = '[Y/n]' if default else '[y/N]'
    answer = input(f'{question} {hint}: ').strip().lower()

    return answer in {'y', 'yes'} if answer else default

def _steps(
    *steps: str
) -> None:

    console = _console()
    console.print()

    for number, step in enumerate(steps, start = 1): console.print(rich.text.Text.assemble((f'{number}.', 'bold'), f' {step}'))

def _link(
    url: str
) -> None:

    console = _console()
    console.print()
    console.print(rich.text.Text.assemble('>> ', (url, rich.style.Style(underline = True, link = url))))

def _report(
    status: str,
    message: str,
    *,
    blank: bool = False
) -> None:

    _console(stderr = status in {'WARNING', 'ERROR'}).print(rich.text.Text.assemble('\n' if blank else '', (f'[{status}]', _STATUS_STYLES[status]), f' {message}'))

def _console(
    *,
    stderr: bool = False
) -> rich.console.Console:

    return rich.console.Console(stderr = stderr, soft_wrap = True, highlight = False, markup = False, emoji = False)
