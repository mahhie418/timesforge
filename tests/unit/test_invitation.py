import datetime
import typing

import pytest
import slack_sdk

import timesforge.slack.invitation
import timesforge.storage
import timesforge.times.exclusion
import timesforge.times.invitation

CREATION = datetime.datetime(2026, 10, 26, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(minutes = 1)

@pytest.fixture
def invitations(
    database: timesforge.storage.Database
) -> timesforge.times.invitation.InvitationIO:

    return timesforge.times.invitation.InvitationIO(database)

@pytest.fixture
def inviter(
    writer: slack_sdk.web.WebClient,
    slack: slack_sdk.web.WebClient,
    invitations: timesforge.times.invitation.InvitationIO
) -> timesforge.slack.invitation.Inviter:

    return timesforge.slack.invitation.Inviter(slack, writer, invitations, 'TXXX')

def test_invitation_member_eligibility(
    workspace: dict[str, typing.Any]
) -> None:

    assert [user['id'] for user in workspace['users'] if timesforge.slack.invitation.eligible(user)] == ['UXXX1', 'UXXX2', 'UXXX3', 'UXXX4']

def test_invitation_channel_members(
    workspace: dict[str, typing.Any],
    invitations: timesforge.times.invitation.InvitationIO,
    inviter: timesforge.slack.invitation.Inviter
) -> None:

    assert inviter.invite('CXXX1', CREATION) == []
    assert workspace['members']['CXXX1'] == ['UXXX1', 'UXXX2', 'UXXXB', 'UXXX3', 'UXXX4']
    assert invitations.find('TXXX', 'CXXX1') == [timesforge.times.invitation.Invitation(user_id = user_id, status = 'invited', attempt_count = 1, update = CREATION) for user_id in ('UXXX3', 'UXXX4')]

def test_invitation_member_refusal(
    workspace: dict[str, typing.Any],
    invitations: timesforge.times.invitation.InvitationIO,
    inviter: timesforge.slack.invitation.Inviter
) -> None:

    workspace['refusals'] = {'UXXX3': 'xxx'}

    assert inviter.invite('CXXX1', CREATION) == ['UXXX3']
    assert workspace['members']['CXXX1'] == ['UXXX1', 'UXXX2', 'UXXXB', 'UXXX4']

    workspace['refusals'] = {}

    assert inviter.invite('CXXX1', CHANGE) == []
    assert workspace['members']['CXXX1'] == ['UXXX1', 'UXXX2', 'UXXXB', 'UXXX4', 'UXXX3']
    assert invitations.find('TXXX', 'CXXX1') == [timesforge.times.invitation.Invitation(user_id = 'UXXX3', status = 'invited', attempt_count = 2, update = CHANGE), timesforge.times.invitation.Invitation(user_id = 'UXXX4', status = 'invited', attempt_count = 1, update = CREATION)]

def test_invitation_member_excluded(
    database: timesforge.storage.Database,
    workspace: dict[str, typing.Any],
    inviter: timesforge.slack.invitation.Inviter
) -> None:

    exclusion = timesforge.times.exclusion.Exclusion(user_id = 'UXXX3', reason = 'xxx', owner_id = 'UXXX0', creation = CREATION)

    timesforge.times.exclusion.ExclusionIO(database).add('TXXX', exclusion)

    inviter.invite('CXXX1', CREATION)

    assert 'UXXX3' in workspace['members']['CXXX1']
