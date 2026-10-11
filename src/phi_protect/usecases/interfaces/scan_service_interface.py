from abc import ABC, abstractmethod

from phi_protect.usecases.dtos import ScanResult


class ScanServiceInterface(ABC):
    @abstractmethod
    async def scan_text(self, text: str) -> ScanResult:
        pass
