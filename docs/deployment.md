# Running TimesForge in a workspace

## The settings file

`timesforge setup` writes the settings file, and you can also write it by hand. Where it is depends on the system, as the README shows. It looks like this, with your own values:

```
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-…
SLACK_USER_TOKEN=xoxp-…
TIMESFORGE_OWNER_ID=U0123ABCDE
TIMESFORGE_CHANNEL_ID_WELCOME=C0123ABCDEF
```

Leave out `SLACK_USER_TOKEN` where members may create public channels. The file holds the tokens, so keep it to yourself: setup lets only you read it on macOS and Linux, and if you write it by hand there, run `chmod 600` on it. `timesforge doctor` shows which file it read and checks the values.

## Existing times channels

Times channels that members created by hand before TimesForge are unknown to it: their holders have no record, so they could create another. Import them once, before the members start using App Home. `timesforge setup` lists the channels in Slack whose names start with `times_` and that TimesForge does not know yet, with their IDs.

Write a JSON file that maps the ID of each channel to the member ID of its holder, as the README shows, then run `timesforge import --mapping FILE --dry-run`. It prints one line for each channel, and changes nothing:

| Line | Meaning |
|---|---|
| `import` | The channel can be imported. |
| `skip (registered)` | TimesForge has the channel with the same holder already. |
| `error (channel_not_found)` | Slack has no channel with the ID, or the bot cannot see it. |
| `error (user_not_found)` | Slack has no user with the ID. |
| `error (private)` | The channel is private. Only public channels are times channels. |
| `error (name)` | The name of the channel is not `times_` followed by a first name in lower-case letters A to Z, with hyphens only between them. |
| `error (holder)` | The holder is not a member of the workspace, such as a guest or a deactivated user. |
| `error (registered)` | TimesForge has the channel with another holder. The owner changes the holder in App Home instead. |
| `error (held)` | The holder holds another times channel that is not deleted. |
| `error (duplicate)` | The file names the holder for more than one channel. |

When every line is `import` or `skip`, run the same command with `--apply`. It imports all the channels in one go, or none of them when any line is an error, and prints how many it imported. Running it again imports nothing twice.

An imported channel is held as if its holder had created it: they cannot create another, and the history records the import. An archived channel is imported as archived. Importing invites nobody, because the members of a channel created by hand chose to join it. The owner can check the holders later in App Home (**Imported channels**, then **Review**) and change them; the history keeps the former holder.

## Welcome messages

When someone joins the welcome channel, the bot sends them a direct message if all of these hold:

- They are a member of the workspace, not a guest or a bot.
- They hold no times channel, deleted ones included, and have not asked for one.
- The owner has not excluded them.
- They have not been sent a welcome message before.

TimesForge records the message before it sends it. So an event that Slack sends again, a member who leaves the channel and joins it again, or a restart of the Slack app sends nothing more. If the connection breaks or Slack fails while the message is being sent, nobody knows whether Slack took it, and TimesForge does not send it again. Instead, when the Slack app starts, it looks for the message in the conversation with the member, by the metadata that every welcome message carries. If Slack does not have the message, it stays unsent, because Slack might still deliver it. In that rare case the member gets no welcome message, but App Home still invites them to create a times channel.

Once the member has a times channel, TimesForge edits their welcome message to link to it, so that it no longer asks them to create one. If Slack refuses the edit, the message stays as it was, and App Home still shows the channel.

On the Free plan, Slack shows only the last 90 days of messages, so an old welcome message may no longer show. The bot has to stay in the welcome channel to notice who joins it; `timesforge doctor` checks that it is.

## Backing up the database

The database, `timesforge.sqlite3` in the data folder, holds the times channels and their holders, the requests, the exclusions, the recreation grants, the welcome messages and the history. Slack keeps none of this, so back it up regularly, and after the owner changes exclusions or grants.

The database is written while the Slack app runs, so a plain copy of the file may be incomplete. To back it up while the app runs, use the `.backup` command of the `sqlite3` tool, which comes with macOS:

```sh
sqlite3 ~/Library/"Application Support"/timesforge/timesforge.sqlite3 ".backup 'timesforge-backup.sqlite3'"
```

Otherwise, stop the Slack app first, then copy `timesforge.sqlite3` together with `timesforge.sqlite3-wal` and `timesforge.sqlite3-shm` if they exist.

To restore a backup:

1. Stop the Slack app, with `timesforge stop` or with Ctrl+C if it runs in a terminal.
2. Replace `timesforge.sqlite3` in the data folder with the backup, and delete `timesforge.sqlite3-wal` and `timesforge.sqlite3-shm` if they exist.
3. Start the Slack app again, with `timesforge setup`, pressing Enter to keep each answer, which also registers it to start at login again, or with `timesforge start`.

When it starts, the Slack app checks the times channels in the backup against Slack, and records what was archived, restored, renamed or deleted since the backup. What TimesForge alone knew is as it was at the backup, with its history up to then. Times channels created since the backup are not in it; import them, as setup lists them. Exclusions and recreation grants changed since the backup have to be made again by the owner.

## Recovering from failures

- **The app stopped.** If setup registered it to start at login, the system starts it again whenever it stops with an error. When it starts, it catches up with Slack: it creates the times channels that were approved but not yet created, finishes invitations that were cut off, and looks for welcome messages whose sending was cut off.
- **A creation was cut off.** If the connection broke or Slack failed while a channel was being created, nobody knows whether Slack created it. TimesForge looks for the channel in Slack before it tries again, so that no request ever creates two channels.
- **Slack refused a creation.** App Home shows the member the reason, and they can try again.
- **A token stopped working**, for example after the app was reinstalled. `timesforge doctor` shows which check fails; run `timesforge setup` again and paste the new token.
- **The bot left the welcome channel.** `timesforge doctor` reports it; invite the bot again with `/invite @TimesForge`.
- **Anything else.** The output of the Slack app is in `start.log` in the data folder when setup registered it to start at login, or in the terminal that runs `timesforge start`.

To move TimesForge to another computer, run `timesforge stop` on the old one, install TimesForge on the new one, copy the settings file and a backup of the database to where the README places them on that system, and run `timesforge setup` there. Run it on one computer only.
