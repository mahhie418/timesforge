# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

import pytest

import timesforge.configuration
import timesforge.slack.permission

USERS_CLASSIFIED = [('UXXX1', 'owner'), ('UXXX2', 'member')]

@pytest.mark.parametrize(('user', 'role'), USERS_CLASSIFIED)
def test_permission_user_role(
    user: str,
    role: timesforge.slack.permission.Role
) -> None:

    settings = timesforge.configuration.load({'TIMESFORGE_OWNER_ID': 'UXXX1'})

    assert timesforge.slack.permission.role(settings, user) == role
