"""
Background Processing System for DIGEFx Monitor

Sistema híbrido com auto-startup e controle opcional via API
"""

from .background_manager import background_manager
from .event_system import EventBus, AlertEvent
from .camera_alert_processor import CameraAlertProcessor
from .camera_processor import CameraProcessor, CameraConfig

__all__ = [
    "background_manager",
    "EventBus", 
    "AlertEvent",
    "CameraAlertProcessor",
    "CameraProcessor",
    "CameraConfig"
] 