# timesforge

[日本語](README.ja.md)

timesforge lets each member of a Slack workspace create their own public channel, `#times_<first name>`, called a times channel, where they post whatever they like. Members create it themselves from the App Home of timesforge, and timesforge invites the other members of the workspace to it. It works on the Free plan of Slack.

timesforge runs on your own computer as an internal Slack app. It connects to Slack with Socket Mode, so it needs no public address, and it talks only to Slack.

## What it does

- **Times channels from App Home.** A member opens timesforge in Slack, enters their first name, and timesforge creates the channel in the background and invites the members of the workspace. The request is approved without anyone's help unless the name is taken.
- **Welcome messages.** When a member who has no times channel yet joins the welcome channel, such as #welcome, the bot sends them one direct message that links to App Home. Once their times channel is ready, the message is edited to link to it.
- **One each.** Each member can create one times channel. Deleting it does not give the right back, but the owner can let a member create one more.
- **One owner.** The owner chooses another name when one is taken, excludes members from creating times channels, gives recreation grants, corrects the holders of imported channels and reads the history, all in App Home.
- **Following Slack.** Archiving, restoring, renaming and deleting a times channel in Slack show in App Home. Times channels that members created by hand before timesforge can be imported.

## Requirements

- macOS or Windows. timesforge also runs on Linux, but setup does not register it to start at login there.
- [uv](https://docs.astral.sh/uv/), which installs timesforge and the Python that it needs.
- A Slack workspace where you can create and install an app. Where only admins may create public channels, an admin installs it.

## Install

```sh
uv tool install timesforge
```

## Set up

```sh
timesforge setup
```

Setup walks you through four steps and writes your answers to the settings file:

1. **Slack app.** Open the link that setup shows to create the Slack app, whose settings are filled in from the manifest. Follow the numbered steps, then paste the Bot User OAuth Token and the App-Level Token. Where only admins may create public channels, an admin installs the app and you also paste the User OAuth Token; otherwise leave it empty.
2. **Owner.** Paste the member ID of the person who owns timesforge. To copy it, open their profile in Slack and select ⋮ (More), then Copy member ID.
3. **Welcome channel.** Paste the channel ID of the channel that new members join, such as #welcome, and add the bot to it by sending `/invite @timesforge` there. Setup waits until the bot is in the channel; press Enter to check again.
4. **Check and autostart.** Setup checks the settings, the tokens, the database, the owner and the welcome channel, and lists the times channels in Slack that timesforge does not know yet. Then it offers to start the Slack app automatically when you log in. If you decline, it stops an earlier registration, as `timesforge stop` does.

To change an answer, run setup again. Where a question shows the current value in brackets (`keep current` for tokens), press Enter to keep it. [Creating the Slack app](docs/slack.md) explains how to do the first three steps by hand.

## Import existing times channels

If members created times channels by hand before timesforge, import them, so that timesforge knows who holds them. Write a JSON file that maps the ID of each channel to the member ID of its holder:

```json
{"C0123ABCDEF": "U0123ABCDE", "C0456GHIJKL": "U0456FGHIJ"}
```

Then check the file, and import the channels:

```sh
timesforge import --mapping channels.json --dry-run
timesforge import --mapping channels.json --apply
```

`--dry-run` shows for each channel whether it can be imported, and changes nothing. `--apply` imports the channels only if every one of them can be.

## App Home

A member creates their times channel like this:

1. Open timesforge in Slack and go to its Home tab, or select **Create your times** in the welcome message.
2. Select **Create times channel**, enter your first name in letters A to Z and select **Create**.
3. App Home shows the channel once it is created. If the name is taken, the owner chooses another name.

The owner also sees **Owner actions**:

- **Name conflicts.** **Choose name** creates the channel of a member whose name was taken, under another name.
- **Excluded members.** **Change exclusions** excludes a member from creating times channels, with a reason, or lets them create one again.
- **Recreation grants.** **Change grants** lets a member whose times channel was deleted create one more, once.
- **Imported channels.** **Review** changes the holder of an imported channel.
- **History.** **Show history** lists the latest changes to the times channels and to who may create them.

## Settings

timesforge reads `timesforge.env` in your configuration folder. Environment variables take precedence over the file.

| System | Settings file | Data folder |
|---|---|---|
| macOS | `~/Library/Application Support/timesforge/timesforge.env` | `~/Library/Application Support/timesforge` |
| Windows | `%LOCALAPPDATA%\timesforge\timesforge.env` | `%LOCALAPPDATA%\timesforge` |
| Linux | `~/.config/timesforge/timesforge.env` | `~/.local/share/timesforge` |

| Variable | Meaning |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token of the Slack app (`xoxb-…`) |
| `SLACK_APP_TOKEN` | App-Level Token of the Slack app (`xapp-…`) |
| `SLACK_USER_TOKEN` | User OAuth Token of an admin (`xoxp-…`), only where only admins may create public channels. The times channels are then created with it. |
| `TIMESFORGE_OWNER_ID` | Member ID of the owner |
| `TIMESFORGE_CHANNEL_ID_WELCOME` | Channel ID of the channel that new members join, such as #welcome |
| `TIMESFORGE_DATA_DIRECTORY` | Folder for the database. Keep it on a local disk. |
| `TIMESFORGE_LANGUAGE_DISPLAY` | Language of App Home and the welcome messages, `en` or `ja`, for people whose Slack language is neither English nor Japanese |

Restart the Slack app after you change the settings file.

## Commands

| Command | What it does |
|---|---|
| `timesforge setup` | Creates the Slack app, chooses the owner and the welcome channel and starts the Slack app at login, writing the settings file |
| `timesforge start` | Runs the Slack app until it is stopped. `--log FILE` appends the output to a file. |
| `timesforge stop` | Stops the Slack app and stops it from starting at login |
| `timesforge doctor` | Checks the settings, the Slack tokens, the database, the owner and the welcome channel |
| `timesforge import --mapping FILE --dry-run` | Shows whether the times channels in a mapping file can be imported |
| `timesforge import --mapping FILE --apply` | Imports the times channels in a mapping file, when every one of them can be |
| `timesforge manifest` | Prints the manifest for creating the Slack app |

## Running timesforge

App Home, the welcome messages and the creation of times channels work only while the Slack app runs. If setup registered it to start at login, it is already running, and it starts again whenever it stops with an error; its output goes to `start.log` in the data folder. Otherwise, run `timesforge start` and keep it running.

When the Slack app starts, it catches up with what changed in Slack while it was stopped, and it finishes the times channels that it was creating.

Run only one Slack app for a workspace. timesforge refuses to start twice with the same data folder, but if it ran on two computers, Slack would split the events and the button presses between them.

To restart the Slack app, for example after changing the settings file:

- macOS: `launchctl kickstart -k gui/$(id -u)/timesforge`
- Windows: `schtasks /End /TN timesforge`, then `schtasks /Run /TN timesforge`
- Without autostart: stop `timesforge start` with Ctrl+C and run it again.

To stop the Slack app and stop it from starting at login, run `timesforge stop`.

## Notes

- Slack shows the bot, or the admin whose user token created the channel, as the creator of each times channel. timesforge keeps the holder itself, so this does not matter. Such an admin is also a member of every times channel, and may leave them.
- Members who join the workspace later are not invited to the existing times channels. To have them join, add the times channels to the default channels of the workspace, or ask them to join.
- On the Free plan, Slack shows only the last 90 days of messages, so an old welcome message may no longer show. App Home always shows whether a member can create a times channel.
- The settings file holds the Slack tokens, and on macOS and Linux only you can read it.
- The database in the data folder is the only record of who holds which times channel and who may create one. Back it up.
