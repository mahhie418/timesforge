# Times channels and who may create them

## Members and everyone else

timesforge tells members from everyone else by their Slack accounts:

- The primary owner, the owners, the admins and the members of the workspace may create a times channel, and they are invited to the times channels of others.
- Guests, both multi-channel and single-channel, bots, workflow bots, Slackbot, deactivated users, people who were invited but have not joined yet and people from other organisations may not create one, and they are not invited.

App Home tells everyone who is not a member that only members can create a times channel. The welcome message goes to members only.

## The holder

The member who asks for a times channel holds it. timesforge records the holder in its database, whoever Slack shows as the creator of the channel: the bot, or the admin whose user token created it. App Home shows each member the times channels that they hold or held.

## One times channel each

A member may create a times channel when all of these hold:

- The owner has not excluded them.
- They hold no times channel that is not deleted. An archived one still counts.
- They have never created one, or the owner gave them a recreation grant after theirs was deleted, as [Deleted times channels and recreation](recreation.md) explains, and they have not used it yet.

The request is approved at once, without the owner, and the channel is created in the background. Pressing the button again, or two requests at the same time, still create one channel only.

## Names

A times channel is named `times_` followed by the first name of the member in lower case, so `Ab-Cd` gives `#times_ab-cd`. The first name is written in letters A to Z, with hyphens only between them. Nothing is transliterated: a member whose name is written in other characters enters it in letters A to Z. The whole name, `times_` included, may be up to 80 characters long.

If Slack has a channel with the name already, the request waits for the owner, who chooses another name in App Home (**Name conflicts**, then **Choose name**). The member still holds the channel under the new name. If Slack refuses to create the channel for another reason, App Home shows the reason, and the member can try again.

## Invitations

Once a times channel exists, timesforge invites to it the members of the workspace, as listed under the first heading. The members whom the owner excluded are invited too. If the invitations are cut off, timesforge finishes them when it starts again.

People who join the workspace after a times channel was created are not invited to it. To have them join the times channels, add the channels to the default channels of the workspace, or ask them to join.

## The owner

`TIMESFORGE_OWNER_ID` names the one owner of timesforge. Only the owner sees **Owner actions** in App Home, and timesforge checks again that the person is the owner whenever they open or submit an owner action. The owners and the admins of the Slack workspace have no part in timesforge unless one of them is its owner.

To hand the role to someone else, run `timesforge setup` again, or change `TIMESFORGE_OWNER_ID` in the settings file, then restart the Slack app.

## Exclusions

The owner excludes a member from creating times channels in **Excluded members**, with **Change exclusions**. A reason is needed, and the list shows it. An excluded member:

- cannot create a times channel, as App Home tells them;
- gets no welcome message;
- keeps the times channel that they hold, if any;
- is still invited to the times channels of others.

The owner lets them create times channels again in the same place. The history records every exclusion and its end, with the owner who made the change.
