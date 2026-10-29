# Deleted times channels and recreation

## What timesforge follows

timesforge never archives, renames or deletes a times channel itself. When someone does so in Slack, timesforge records it as it happens:

- An archived times channel stays the member's. They cannot create another while it exists, and restoring it in Slack makes it active again.
- A renamed times channel keeps its holder, and App Home shows the new name.
- A deleted times channel stays in App Home as deleted.

When the Slack app starts, it checks every times channel against Slack, so that what changed while it was stopped is recorded too. App Home shows each member their times channels with the date when they were created, archived or deleted, and the history lists the changes for the owner.

## Deleting a times channel

To delete a times channel, delete it in Slack, as someone whom the workspace settings allow to delete channels. There is nothing to do in timesforge.

Deleting the channel does not give the member the right to create another. App Home then tells them that creating another needs permission from the owner, and the welcome message is not sent again.

## Recreation grants

The owner lets a member create one more times channel in **Recreation grants**, with **Change grants**. The owner can give a grant to a member who:

- has created a times channel before;
- holds none that is not deleted;
- is not excluded;
- has no grant that is not used up yet.

The member then sees in App Home that they can create one more, and creates it as before. Creating the channel uses the grant up, so a member who deletes that channel too needs another grant. The owner can revoke a grant that has not been used yet. The history records every grant and revocation, with the owner who made it.

A member whose times channel was imported holds it as if they had created it, so the same applies to them.
