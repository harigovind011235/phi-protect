from fastapi import APIRouter
from pydantic import BaseModel, Field

from phi_protect.handler.dependencies import ScanServiceDep
from phi_protect.usecases.dtos import ScanResult

MAX_TEXT_LENGTH = 200_000

router = APIRouter(tags=["scan"])


class ScanRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_LENGTH)


@router.post("/scan", response_model=ScanResult)
async def scan_text(request: ScanRequest, service: ScanServiceDep) -> ScanResult:
    return await service.scan_text(request.text)
