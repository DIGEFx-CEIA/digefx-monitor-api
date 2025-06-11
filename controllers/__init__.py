"""
Módulo de inicialização dos controladores
"""
from .auth_controller import router as auth_router
from .device_controller import router as device_router
from .camera_controller import router as camera_router
from .alert_controller import router as alert_router
from .terminal_controller import router as terminal_router


def setup_routes(app):
    """Configura todas as rotas da aplicação"""
    app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
    app.include_router(device_router, prefix="/api/v1", tags=["devices"])
    app.include_router(camera_router, prefix="/api/v1", tags=["cameras"])
    app.include_router(alert_router, prefix="/api/v1", tags=["alerts"])
    app.include_router(terminal_router, prefix="/api/v1", tags=["terminal"])


__all__ = [
    'setup_routes',
    'auth_router',
    'device_router', 
    'camera_router',
    'alert_router',
    'terminal_router'
] 