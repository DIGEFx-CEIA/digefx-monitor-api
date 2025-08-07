"""
Sistema de eventos interno para alertas de câmeras
Implementa Publisher/Subscriber pattern para desacoplamento
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum
from models import Camera
import uuid

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EventType(Enum):
    """Tipos de eventos do sistema"""
    CAMERA_ALERT_DETECTED = "camera_alert_detected"
    CAMERA_PROCESSING_STARTED = "camera_processing_started"
    CAMERA_PROCESSING_STOPPED = "camera_processing_stopped"
    CAMERA_STATUS_CHANGED = "camera_status_changed"
    NEW_VIDEO_FILE = "new_video_file"

@dataclass
class AlertEvent:
    """Estrutura de dados para eventos de alerta"""
    event_id: str
    event_type: EventType
    camera_id: int
    camera_name: str
    camera_ip: str
    alert_type_code: str
    alert_type_name: str
    alert_type_id: int
    severity: str
    confidence: float
    detected_at: datetime
    metadata: Dict[str, Any]
    image_path: Optional[str] = None
    video_clip_path: Optional[str] = None

@dataclass
class CameraStatusEvent:
    """Estrutura de dados para eventos de status de câmera"""
    event_id: str
    event_type: EventType
    camera_id: int
    camera_name: str
    status: str  # started, stopped, error
    timestamp: datetime
    metadata: Dict[str, Any]

@dataclass
class NewVideoFileEvent:
    """Estrutura de dados para eventos de novo arquivo de vídeo"""
    event_id: str
    event_type: EventType
    camera: Camera
    file_path: str
    timestamp: datetime
    metadata: Dict[str, Any]

@dataclass
class TriggerDetectionEvent:
    """Estrutura de dados para eventos de detecção acionada"""
    event_id: str
    event_type: EventType
    file_path: str
    timestamp: datetime
    metadata: Dict[str, Any]
    camera: Camera

class EventBus:
    """
    Sistema de eventos centralizado
    Implementa padrão Publisher/Subscriber com suporte a async
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Dict] = []
        self._max_history = 1000
        self._lock = asyncio.Lock()
        
    async def subscribe(self, event_type: EventType, handler: Callable):
        """Registra um handler para um tipo de evento"""
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
            logger.info(f"Handler {handler.__name__} registrado para evento {event_type.value}")
    
    async def unsubscribe(self, event_type: EventType, handler: Callable):
        """Remove um handler de um tipo de evento"""
        async with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                    logger.info(f"Handler {handler.__name__} removido do evento {event_type.value}")
                except ValueError:
                    logger.warning(f"Handler {handler.__name__} não encontrado para evento {event_type.value}")
    
    async def publish(self, event: AlertEvent | CameraStatusEvent | NewVideoFileEvent | TriggerDetectionEvent):
        """Publica um evento para todos os subscribers"""
        event_type = event.event_type
        
        # Adicionar ao histórico
        await self._add_to_history(event)
        
        # Buscar handlers
        handlers = self._subscribers.get(event_type, [])
        
        if not handlers:
            logger.warning(f"Nenhum handler encontrado para evento {event_type.value}")
            return
        
        logger.info(f"Publicando evento {event_type.value} para {len(handlers)} handlers")
        
        # Executar handlers em paralelo
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._safe_call_handler(handler, event))
            tasks.append(task)
        
        # Aguardar todos os handlers
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log de resultados
            for i, result in enumerate(results):
                handler_name = handlers[i].__name__
                if isinstance(result, Exception):
                    logger.error(f"Erro no handler {handler_name}: {result}")
                else:
                    logger.debug(f"Handler {handler_name} executado com sucesso")
    
    async def _safe_call_handler(self, handler: Callable, event: AlertEvent | CameraStatusEvent | NewVideoFileEvent | TriggerDetectionEvent):
        """Executa handler com tratamento de erro"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                # Executar função síncrona em thread pool
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler, event)
        except Exception as e:
            logger.error(f"Erro no handler {handler.__name__}: {e}")
            raise
    
    async def _add_to_history(self, event: AlertEvent | CameraStatusEvent | NewVideoFileEvent | TriggerDetectionEvent):
        """Adiciona evento ao histórico"""
        async with self._lock:
            event_dict = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": datetime.utcnow().isoformat(),
                "data": event.__dict__ if hasattr(event, '__dict__') else str(event)
            }
            
            self._event_history.append(event_dict)
            
            # Manter apenas os últimos N eventos
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
    
    def get_event_history(self, limit: int = 100) -> List[Dict]:
        """Retorna histórico de eventos"""
        return self._event_history[-limit:]
    
    def get_subscriber_count(self, event_type: EventType) -> int:
        """Retorna número de subscribers para um evento"""
        return len(self._subscribers.get(event_type, []))

# Instância global do event bus
event_bus = EventBus()

def create_alert_event(
    camera_id: int,
    camera_name: str,
    camera_ip: str,
    alert_type_code: str,
    alert_type_name: str,
    alert_type_id: int,
    severity: str,
    confidence: float,
    metadata: Dict[str, Any],
    image_path: Optional[str] = None,
    video_clip_path: Optional[str] = None
) -> AlertEvent:
    """Factory function para criar eventos de alerta"""
    return AlertEvent(
        event_id=str(uuid.uuid4()),
        event_type=EventType.CAMERA_ALERT_DETECTED,
        camera_id=camera_id,
        camera_name=camera_name,
        camera_ip=camera_ip,
        alert_type_code=alert_type_code,
        alert_type_name=alert_type_name,
        alert_type_id=alert_type_id,
        severity=severity,
        confidence=confidence,
        detected_at=datetime.utcnow(),
        metadata=metadata,
        image_path=image_path,
        video_clip_path=video_clip_path
    )

def create_camera_status_event(
    camera_id: int,
    camera_name: str,
    status: str,
    metadata: Dict[str, Any]
) -> CameraStatusEvent:
    """Factory function para criar eventos de status"""
    return CameraStatusEvent(
        event_id=str(uuid.uuid4()),
        event_type=EventType.CAMERA_PROCESSING_STARTED if status == "started" else EventType.CAMERA_PROCESSING_STOPPED,
        camera_id=camera_id,
        camera_name=camera_name,
        status=status,
        timestamp=datetime.utcnow(),
        metadata=metadata
    ) 

def create_new_video_file_event(
    file_path: str,
    metadata: Dict[str, Any]
) -> NewVideoFileEvent:
    """Factory function para criar eventos de novo arquivo de vídeo"""
    return NewVideoFileEvent(
        event_id=str(uuid.uuid4()),
        event_type=EventType.NEW_VIDEO_FILE,
        file_path=file_path,
        timestamp=datetime.utcnow(),
        metadata=metadata,
        camera=None  # Será preenchido no handler de vídeo
    )

def create_trigger_detection_event(video_event: NewVideoFileEvent) -> TriggerDetectionEvent:
    """Factory function para criar eventos de detecção acionada"""
    return TriggerDetectionEvent(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TRIGGER_DETECTION,
        file_path=video_event.file_path,
        timestamp=video_event.timestamp,
        metadata=video_event.metadata,
        camera=video_event.camera
    )