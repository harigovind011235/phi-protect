from abc import ABC, abstractmethod

from phi_protect.usecases.dtos import DeidentifiedFile, FileScanResult


class FileServiceInterface(ABC):
    @abstractmethod
    async def scan_file(self, data: bytes) -> FileScanResult:
        pass

    @abstractmethod
    async def deidentify_file(self, data: bytes) -> DeidentifiedFile:
        """Raises UnverifiableFileError when the file cannot be fully checked."""
        pass
