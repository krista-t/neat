from dataclasses import dataclass

from cognite.neat.issues import NeatWarning


@dataclass(frozen=True)
class RegexViolationWarning(NeatWarning):
    """The value '{value}' of {identifier} does not match the {pattern_name} pattern '{pattern}'"""

    extra = "{motivation}"
    value: str
    pattern: str
    identifier: str
    pattern_name: str
    motivation: str | None = None
