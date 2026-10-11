from fastapi import FastAPI

from phi_protect.composition import Container, create_container
from phi_protect.config.settings import create_settings
from phi_protect.handler.errors import register_error_handlers
from phi_protect.handler.routes.files import router as files_router
from phi_protect.handler.routes.health import router as health_router
from phi_protect.handler.routes.scan import router as scan_router


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(
        title="PHI Protect",
        description="Detects and removes PHI before text or files are sent to AI tools",
        version="0.1.0",
    )
    app.state.container = container or create_container(create_settings())
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(scan_router)
    app.include_router(files_router)
    return app
