from phi_protect.domain.models import Finding

from .labeled_values import find_labeled_values
from .patterns import find_pattern_matches
from .us_states import US_STATE_CODES


def find_rule_matches(text: str) -> list[Finding]:
    """Rule-based PHI candidates. Runs alongside any detector, so swapping detectors keeps them."""
    return [*find_labeled_values(text), *find_pattern_matches(text)]


__all__ = [
    "US_STATE_CODES",
    "find_rule_matches",
]
