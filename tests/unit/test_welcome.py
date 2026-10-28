import datetime
import typing

import pytest
import slack_sdk

import timesforge.slack.welcome
import timesforge.storage
import timesforge.times.onboarding

CREATION = datetime.datetime(2026, 10, 29, 15, 0, tzinfo = datetime.UTC)
CHANGE = CREATION + datetime.timedelta(minutes = 1)

BLOCKS = [{'type': 'section', 'text': {'type': 'mrkdwn', 'text': 'xxx'}}]
METADATA = {'event_type': 'timesforge_welcome', 'event_payload': {'user_id': 'UXXX2'}}

DROPS_LOST = [(['lost'], 'sent'), (['dropped'], 'unknown'), ([500], 'unknown')]

@pytest.fixture
def store(
    database: timesforge.storage.Database
) -> timesforge.times.onboarding.OnboardingIO:

    return timesforge.times.onboarding.OnboardingIO(database)

@pytest.fixture
def greeter(
    slack: slack_sdk.web.WebClient,
    store: timesforge.times.onboarding.OnboardingIO
) -> timesforge.slack.welcome.Greeter:

    return timesforge.slack.welcome.Greeter(slack, slack, store, 'TXXX')

def greet(
    greeter: timesforge.slack.welcome.Greeter,
    now: datetime.datetime = CREATION
) -> timesforge.times.onboarding.Message | None:

    return greeter.greet('UXXX2', channel_id = 'CXXX0', event_id = 'EvXXX', text = 'xxx', blocks = BLOCKS, now = now)

def test_welcome_message_delivery(
    workspace: dict[str, typing.Any],
    greeter: timesforge.slack.welcome.Greeter
) -> None:

    message = greet(greeter)

    assert message is not None
    assert (message.status, message.conversation_id, message.message_ts, message.delivery) == ('sent', 'DUXXX2', '1793026800.000001', CREATION)
    assert workspace['messages']['DUXXX2'] == [{'type': 'message', 'user': 'UXXXB', 'text': 'xxx', 'ts': '1793026800.000001', 'metadata': METADATA}]
    assert greet(greeter, CHANGE) == message
    assert len(workspace['messages']['DUXXX2']) == 1

def test_welcome_slack_refusal(
    workspace: dict[str, typing.Any],
    greeter: timesforge.slack.welcome.Greeter
) -> None:

    workspace['drops'] = ['restricted_action']

    message = greet(greeter)

    assert message is not None
    assert (message.status, message.error) == ('failed', 'restricted_action')

    message = greet(greeter, CHANGE)

    assert message is not None
    assert (message.status, message.error) == ('sent', None)

@pytest.mark.parametrize(('drops', 'status'), DROPS_LOST)
def test_welcome_result_unknown(
    workspace: dict[str, typing.Any],
    greeter: timesforge.slack.welcome.Greeter,
    drops: list[str | int],
    status: timesforge.times.onboarding.Status
) -> None:

    workspace['drops'] = list(drops)

    message = greet(greeter)

    assert message is not None
    assert message.status == 'unknown'
    assert greet(greeter, CHANGE) == message

    message = greeter.recover('UXXX2', CHANGE)

    assert message is not None
    assert message.status == status
    assert len(workspace['messages'].get('DUXXX2', [])) == (status == 'sent')

def test_welcome_recovery_skip(
    greeter: timesforge.slack.welcome.Greeter
) -> None:

    message = greet(greeter)

    assert greeter.recover('UXXX2', CHANGE) == message
    assert greeter.recover('UXXX3', CHANGE) is None
