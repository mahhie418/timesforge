# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Names of times channels, made from the first names that members enter."""

import re
import typing

PREFIX = 'times_'

NAME_LENGTH_MAXIMUM = 80

type Reason = typing.Literal['empty', 'characters', 'length']

_PATTERN_FIRST_NAME = re.compile(r'[A-Za-z]+(?:-[A-Za-z]+)*')

class NameInvalidError(ValueError):

    """Raised when a first name cannot make the name of a times channel.

    Attributes:
        reason: Why the first name was refused: it is empty, it has characters other than letters A to Z and hyphens between them, or it is too long.
    """

    def __init__(
        self,
        reason: Reason,
        message: str
    ) -> None:

        """Initialises the error.

        Args:
            reason: Why the first name was refused.
            message: Explanation of the problem.
        """

        super().__init__(message)

        self.reason = reason

def sanitise(
    first_name: str
) -> str:

    """Makes the name of a times channel from a first name.

    Spaces around the first name are removed and capital letters become
    lower case. Nothing is transliterated, so the first name must already be
    written in letters A to Z, with hyphens only between them.

    Args:
        first_name: First name as the member entered it.

    Returns:
        The name of the channel: `PREFIX` followed by the first name.

    Raises:
        NameInvalidError: The first name is empty, has other characters, or
                          makes a name longer than `NAME_LENGTH_MAXIMUM`.
    """

    name = first_name.strip()

    if not name: raise NameInvalidError('empty', 'Enter a first name')
    if not _PATTERN_FIRST_NAME.fullmatch(name): raise NameInvalidError('characters', 'Write the first name in letters A to Z, with hyphens only between them')
    if len(channel := f'{PREFIX}{name.lower()}') > NAME_LENGTH_MAXIMUM: raise NameInvalidError('length', f'Shorten the first name to {NAME_LENGTH_MAXIMUM - len(PREFIX)} characters or fewer')

    return channel
