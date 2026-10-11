import uvicorn

from phi_protect.composition import create_container
from phi_protect.config.settings import create_settings
from phi_protect.handler.app import create_app

settings = create_settings()
app = create_app(create_container(settings))

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
