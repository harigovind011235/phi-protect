from fastapi import APIRouter, Response, UploadFile

from phi_protect.config.settings import Settings
from phi_protect.handler.dependencies import FileServiceDep, SettingsDep
from phi_protect.usecases.dtos import FileScanResult

router = APIRouter(tags=["files"])


@router.post("/scan-file", response_model=FileScanResult)
async def scan_file(
    file: UploadFile, service: FileServiceDep, settings: SettingsDep
) -> FileScanResult:
    return await service.scan_file(await _read(file, settings))


@router.post("/deidentify-file", response_model=None)
async def deidentify_file(
    file: UploadFile, service: FileServiceDep, settings: SettingsDep
) -> Response:
    result = await service.deidentify_file(await _read(file, settings))
    # The original file name is not reused: file names can contain patient names too.
    headers = {"Content-Disposition": f'attachment; filename="deidentified.{result.extension}"'}
    return Response(content=result.content, media_type=result.media_type, headers=headers)


async def _read(file: UploadFile, settings: Settings) -> bytes:
    # One byte over the limit is enough for the use case to reject it without reading it all.
    return await file.read(settings.max_file_bytes + 1)
