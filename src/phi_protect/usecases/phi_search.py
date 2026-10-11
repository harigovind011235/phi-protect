from phi_protect.domain.models import Finding
from phi_protect.domain.policy import resolve_findings
from phi_protect.domain.rules import find_rule_matches
from phi_protect.usecases.ports.detectors import PhiDetector


async def find_phi(detector: PhiDetector, text: str) -> list[Finding]:
    """Shared by the text and file use cases: detector candidates plus domain rules, then policy."""
    if not text.strip():
        return []
    candidates = [*await detector.detect(text), *find_rule_matches(text)]
    return resolve_findings(text, candidates)
