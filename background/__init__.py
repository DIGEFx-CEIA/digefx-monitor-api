"""
Módulo de inicialização dos serviços de background
"""
from .serial_monitor import start_serial_monitoring
from .host_monitor import start_host_monitoring
from .camera_monitor import start_camera_monitoring


def start_all_background_services():
    """Inicia todos os serviços de background"""
    start_serial_monitoring()
    start_host_monitoring()
    start_camera_monitoring()
    print("All background services started")


__all__ = [
    'start_all_background_services',
    'start_serial_monitoring',
    'start_host_monitoring',
    'start_camera_monitoring'
] 