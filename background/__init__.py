"""
Background Processing System for DIGEFx Monitor

Sistema híbrido com auto-startup e controle opcional via API
"""

from .background_manager import background_manager
from .event_system import EventBus, AlertEvent
from .event_handler_manager import EventHandlerManager

__all__ = [
    "background_manager",
    "EventBus", 
    "AlertEvent",
    "EventHandlerManager"
] 