from typing import Annotated

from fastapi import Depends, Request

from phi_protect.config.settings import Settings
from phi_protect.usecases.interfaces import FileServiceInterface, ScanServiceInterface


def get_settings(request: Request) -> Settings:
    return request.app.state.container.settings


def get_scan_service(request: Request) -> ScanServiceInterface:
    return request.app.state.container.scan_service


def get_file_service(request: Request) -> FileServiceInterface:
    return request.app.state.container.file_service


SettingsDep = Annotated[Settings, Depends(get_settings)]
ScanServiceDep = Annotated[ScanServiceInterface, Depends(get_scan_service)]
FileServiceDep = Annotated[FileServiceInterface, Depends(get_file_service)]
