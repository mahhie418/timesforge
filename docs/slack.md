# Creating the Slack app

TimesForge runs as a Slack app that you create in your own workspace from the manifest of TimesForge. The app uses Socket Mode, so it needs no public address. `timesforge setup` shows a link to the page that creates the app with the manifest filled in; this page explains how to create the app by hand.

## Create the app

1. Run `timesforge manifest` and copy what it prints.
2. Open https://api.slack.com/apps, select **Create New App**, then **From a manifest**.
3. Select the workspace, then select **Next**.
4. On the **JSON** tab, replace the manifest with the one that you copied, then select **Next** and **Create**.

## Install the app

In **Basic Information**, select **Install to Workspace** and allow the access that the app asks for. If the workspace requires approval for apps, an admin of the workspace has to approve the app first.

Who installs the app depends on who may create public channels in the workspace, which its owners set in the workspace settings, on the Free plan too:

- If members may create public channels, anyone who may install apps can install it. The bot creates the times channels.
- If only admins may create public channels, an admin installs it. The bot may not create channels there either, so TimesForge creates the times channels with the user token of that admin.

## Note the tokens

- In **OAuth & Permissions**, the **Bot User OAuth Token**, which starts with `xoxb-`, goes to `SLACK_BOT_TOKEN`.
- In **Basic Information**, under **App-Level Tokens**, select **Generate Token and Scopes**. Name the token, add the `connections:write` scope and select **Generate**. The token, which starts with `xapp-`, goes to `SLACK_APP_TOKEN`.
- Only if only admins may create public channels: in **OAuth & Permissions**, the **User OAuth Token**, which starts with `xoxp-`, goes to `SLACK_USER_TOKEN`. It belongs to the admin who installed the app, and TimesForge checks that this person is an admin. Leave it out otherwise.

## Note the owner

The member ID of the person who owns TimesForge goes to `TIMESFORGE_OWNER_ID`. To copy it, open their profile in Slack and select ⋮ (More), then **Copy member ID**. The owner must be a member of the workspace, not a guest.

## Choose the welcome channel

The ID of the channel that new members join, such as #welcome, goes to `TIMESFORGE_CHANNEL_ID_WELCOME`. To copy it, open the channel, select its name at the top and copy the channel ID at the bottom of **About**.

Then add the bot to the channel: in the channel, send `/invite @TimesForge`. The bot learns who joins only the channels that it is in. It posts nothing there; it sends each new member a direct message instead.

Write these values to the settings file, as the README describes, or paste them when `timesforge setup` asks for them.

## What the app may do

| Scope | What TimesForge does with it |
|---|---|
| `channels:manage` (bot) | Creates the times channels where members may create channels, and invites the members to them |
| `channels:read` (bot) | Reads the public channels and their members, and learns when a channel is archived, restored, renamed or deleted, or when someone joins the welcome channel |
| `chat:write` (bot) | Sends the welcome messages and edits them once the times channel is ready |
| `im:history` (bot) | Looks for a welcome message whose sending was cut off, so that it is not sent twice |
| `im:write` (bot) | Opens the direct message conversation with a new member |
| `users:read` (bot) | Tells members from guests, bots and deactivated users |
| `channels:write` (user) | Creates the times channels with the token of an admin, where only admins may create channels |

## Update the app

When a new version of TimesForge changes the manifest, open **App Manifest** in the settings of the app, replace the manifest with what `timesforge manifest` prints, and select **Save Changes**. If Slack asks you to reinstall the app, reinstall it and allow the new access. Where TimesForge uses the user token of an admin, the same admin reinstalls the app; if another admin does, write their User OAuth Token to `SLACK_USER_TOKEN`.
