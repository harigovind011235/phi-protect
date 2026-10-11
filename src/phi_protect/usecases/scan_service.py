from phi_protect.domain.models import Decision
from phi_protect.domain.policy import decide, deidentify
from phi_protect.usecases.dtos import DetectedEntity, ScanResult
from phi_protect.usecases.interfaces import ScanServiceInterface
from phi_protect.usecases.phi_search import find_phi
from phi_protect.usecases.ports.detectors import PhiDetector


class ScanService(ScanServiceInterface):
    def __init__(self, detector: PhiDetector):
        self._detector = detector

    async def scan_text(self, text: str) -> ScanResult:
        findings = await find_phi(self._detector, text)
        return ScanResult(
            has_phi=decide(findings) == Decision.BLOCK,
            entities=[
                DetectedEntity(f.entity_type.value, f.start, f.end, f.score) for f in findings
            ],
            deidentified_text=deidentify(text, findings),
        )
