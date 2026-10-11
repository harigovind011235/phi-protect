from abc import ABC, abstractmethod

from phi_protect.domain.models import Finding


class PhiDetector(ABC):
    """Finds PHI candidates in text, e.g. with an NER model.

    Returns raw candidates only; allowlisting, merging and blocking are domain policy applied by
    the use case, so they stay the same whichever detector is plugged in.
    """

    @abstractmethod
    async def detect(self, text: str) -> list[Finding]:
        pass
