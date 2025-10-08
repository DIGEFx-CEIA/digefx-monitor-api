"""
Gerenciador simplificado de handlers de eventos
Substitui o CameraAlertProcessor com foco apenas na inicialização de handlers
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from .event_system import EventType
from .handlers import (
    MQTTHandler, AMQPHandler, DatabaseHandler, FrigateHandler, NewVideoHandler, DetectionHandler, StatusHandler
)
from .event_system import event_bus

logger = logging.getLogger(__name__)


class EventHandlerManager:
    """
    Gerenciador simplificado para handlers de eventos
    
    Responsável apenas por:
    - Inicializar handlers de eventos (Database, NewVideo, Detection, MQTT, AMQP, Frigate)
    - Registrar handlers no EventBus
    - Gerenciar lifecycle dos handlers
    """
    
    def __init__(self):
        self.handlers = {}
        self.is_initialized = False
        self.start_time = None
    
    async def initialize(self, handler_configs: Dict[str, Dict[str, Any]] = None):
        """Inicializa todos os handlers de eventos"""
        if self.is_initialized:
            logger.warning("EventHandlerManager já está inicializado")
            return
        
        try:
            logger.info("🔄 Inicializando EventHandlerManager...")
            self.start_time = datetime.utcnow()
            
            # Inicializar handlers
            await self._initialize_handlers(handler_configs or {})
            
            self.is_initialized = True
            logger.info("✅ EventHandlerManager inicializado com sucesso!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar EventHandlerManager: {e}")
            raise
    
    async def cleanup(self):
        """Limpa recursos dos handlers"""
        try:
            logger.info("🛑 Finalizando EventHandlerManager...")
            
            # Limpar handlers
            for handler_name, handler in self.handlers.items():
                try:
                    if hasattr(handler, 'cleanup'):
                        await handler.cleanup()
                    logger.info(f"✅ Handler {handler_name} finalizado")
                except Exception as e:
                    logger.error(f"❌ Erro ao finalizar handler {handler_name}: {e}")
            
            self.handlers.clear()
            self.is_initialized = False
            
            logger.info("✅ EventHandlerManager finalizado!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao finalizar EventHandlerManager: {e}")
    
    async def _initialize_handlers(self, handler_configs: Dict[str, Dict[str, Any]]):
        """Inicializa os handlers essenciais"""
        try:
            # 1. Database Handler (sempre ativo - salva alertas no banco)
            self.handlers['database'] = DatabaseHandler()
            await self.handlers['database'].initialize()
            logger.info("✅ DatabaseHandler inicializado")
            
            # 2. NewVideo Handler (processa arquivos de vídeo do Frigate)
            self.handlers['new_video'] = NewVideoHandler()
            await self.handlers['new_video'].initialize()
            logger.info("✅ NewVideoHandler inicializado")
            
            # 3. Detection Handler (executa YOLO nos vídeos)
            self.handlers['detection'] = DetectionHandler()
            await self.handlers['detection'].initialize()
            logger.info("✅ DetectionHandler inicializado")
            
            # 4. Status Handler (monitora sistema e comunica com ESP32)
            self.handlers['status'] = StatusHandler()
            await self.handlers['status'].initialize()
            logger.info("✅ StatusHandler inicializado")
            
            # 5. MQTT Handler (se configurado)
            if 'mqtt' in handler_configs:
                config = handler_configs['mqtt']
                self.handlers['mqtt'] = MQTTHandler(
                    broker_host=config.get('broker_host', 'localhost'),
                    broker_port=config.get('broker_port', 1883),
                    username=config.get('username'),
                    password=config.get('password')
                )
                await self.handlers['mqtt'].initialize()
                logger.info("✅ MQTTHandler inicializado")
            
            # 5. AMQP Handler (se configurado)
            if 'amqp' in handler_configs:
                config = handler_configs['amqp']
                self.handlers['amqp'] = AMQPHandler(
                    amqp_url=config.get('amqp_url', 'amqp://guest:guest@localhost:5672/')
                )
                await self.handlers['amqp'].initialize()
                logger.info("✅ AMQPHandler inicializado")
            
            # 6. Frigate Handler (se configurado)
            if 'frigate' in handler_configs:
                config = handler_configs['frigate']
                self.handlers['frigate'] = FrigateHandler(
                    frigate_base_url=config.get('frigate_base_url', 'http://localhost:5000')
                )
                await self.handlers['frigate'].initialize()
                logger.info("✅ FrigateHandler inicializado")
            
            # Registrar handlers no EventBus
            await self._register_handlers_in_event_bus()
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar handlers: {e}")
            raise
    
    async def _register_handlers_in_event_bus(self):
        """Registra todos os handlers no EventBus"""
        try:
            # Registrar handlers de alertas de câmera
            alert_handlers = ['database', 'mqtt', 'amqp', 'frigate']
            for handler_name in alert_handlers:
                if handler_name in self.handlers:
                    await event_bus.subscribe(
                        EventType.CAMERA_ALERT_DETECTED, 
                        self.handlers[handler_name].handle_event
                    )
                    logger.info(f"🔗 Handler {handler_name} registrado para CAMERA_ALERT_DETECTED")
            
            # Registrar handler de novos vídeos
            if 'new_video' in self.handlers:
                await event_bus.subscribe(
                    EventType.NEW_VIDEO_FILE, 
                    self.handlers['new_video'].handle_event
                )
                logger.info("🔗 NewVideoHandler registrado para NEW_VIDEO_FILE")
            
            # Registrar handler de detecção
            if 'detection' in self.handlers:
                await event_bus.subscribe(
                    EventType.TRIGGER_DETECTION, 
                    self.handlers['detection'].handle_event
                )
                logger.info("🔗 DetectionHandler registrado para TRIGGER_DETECTION")
            
        except Exception as e:
            logger.error(f"❌ Erro ao registrar handlers no EventBus: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador"""
        uptime_seconds = 0.0
        if self.start_time:
            uptime = datetime.utcnow() - self.start_time
            uptime_seconds = uptime.total_seconds()
        
        # Status dos handlers
        handlers_status = {}
        for handler_name, handler in self.handlers.items():
            handlers_status[handler_name] = {
                "active": True,
                "type": handler.__class__.__name__,
                "initialized": hasattr(handler, 'is_initialized') and getattr(handler, 'is_initialized', True)
            }
        
        return {
            "is_initialized": self.is_initialized,
            "handlers_count": len(self.handlers),
            "uptime_seconds": uptime_seconds,
            "handlers_status": handlers_status,
            "start_time": self.start_time.isoformat() if self.start_time else None
        }
    
    def is_ready(self) -> bool:
        """Verifica se o gerenciador está pronto"""
        return self.is_initialized and len(self.handlers) > 0