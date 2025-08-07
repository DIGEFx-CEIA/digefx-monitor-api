"""
Coordenador principal do sistema de processamento de alertas de câmeras
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
from .event_system import  EventType
from .camera_processor import CameraProcessor, CameraConfig, CameraProcessorFactory
from .handlers import (
    MQTTHandler, AMQPHandler, DatabaseHandler, FrigateHandler, NewVideoHandler, DetectionHandler
)
from models import Camera, AlertType, SessionLocal
from .event_system import event_bus

logger = logging.getLogger(__name__)

class CameraAlertProcessor:
    """
    Coordenador principal do sistema de processamento de alertas
    
    Responsável por:
    - Gerenciar processadores individuais de câmeras
    - Coordenar handlers de eventos (Database, Frigate, MQTT, AMQP)
    - Monitorar status geral do sistema
    """
    
    def __init__(self):
        self.camera_processors: Dict[int, CameraProcessor] = {}
        self.handlers = {}
        self.is_running = False
        self.start_time = None
        self.stats = {
            "total_alerts_processed": 0,
            "cameras_being_processed": 0,
            "uptime_seconds": 0.0,
            "last_check": None
        }
        self._stop_event = asyncio.Event()
        self._check_interval = 30  # segundos
        self._max_concurrent_cameras = 10
    
    async def initialize(self, handler_configs: Dict[str, Dict[str, Any]] = None, 
                        check_interval: int = 30, max_concurrent_cameras: int = 10):
        """Inicializa o processador com configurações"""
        self._check_interval = check_interval
        self._max_concurrent_cameras = max_concurrent_cameras
        
        # Inicializar handlers
        await self._initialize_handlers(handler_configs or {})
        
        logger.info("CameraAlertProcessor inicializado")
    
    async def start_processing(self):
        """Inicia o processamento de alertas"""
        if self.is_running:
            logger.warning("Processamento de alertas já está ativo")
            return
        
        self.is_running = True
        self._stop_event.clear()
        self.start_time = datetime.utcnow()
        
        logger.info("🚨 Iniciando processamento de alertas...")
        
        try:
            # Inicializar handlers se não foram inicializados
            if not self.handlers:
                await self._initialize_handlers({})
            
            # Iniciar loop principal
            await self._main_processing_loop()
            
        except Exception as e:
            logger.error(f"Erro no processamento de alertas: {e}")
        finally:
            self.is_running = False
            logger.info("Processamento de alertas finalizado")
    
    async def stop_processing(self):
        """Para o processamento de alertas"""
        if not self.is_running:
            return
        
        logger.info("🛑 Parando processamento de alertas...")
        self._stop_event.set()
        
        # Parar todos os processadores de câmera
        for camera_id, processor in self.camera_processors.items():
            try:
                await processor.stop_processing()
                logger.info(f"Processador da câmera {camera_id} parado")
            except Exception as e:
                logger.error(f"Erro ao parar processador da câmera {camera_id}: {e}")
        
        self.camera_processors.clear()
        
        # Aguardar o loop principal parar
        for _ in range(50):  # 5 segundos
            if not self.is_running:
                break
            await asyncio.sleep(0.1)
    
    async def _main_processing_loop(self):
        """Loop principal que monitora câmeras e gerencia processadores"""
        while not self._stop_event.is_set():
            try:
                # await self._check_and_update_cameras()
                self._update_stats()
                
                # Aguardar próxima verificação
                await asyncio.sleep(self._check_interval)
                
            except Exception as e:
                logger.error(f"Erro no loop principal: {e}")
                await asyncio.sleep(5)  # Aguardar antes de tentar novamente
    
    async def _check_and_update_cameras(self):
        """Verifica câmeras ativas e atualiza processadores"""
        try:
            db = SessionLocal()
            
            # Buscar câmeras ativas
            active_cameras = db.query(Camera).filter(Camera.is_active == True).all()
            
            # Buscar tipos de alerta ativos
            alert_types = db.query(AlertType).filter(AlertType.is_active == True).all()
            alert_types_dict = {at.code: {
                "id": at.id,
                "name": at.name,
                "code": at.code,
                "icon": at.icon,
                "color": at.color
            } for at in alert_types}
            
            db.close()
            
            # IDs das câmeras ativas
            active_camera_ids = {camera.id for camera in active_cameras}
            
            # Parar processadores de câmeras inativas
            for camera_id in list(self.camera_processors.keys()):
                if camera_id not in active_camera_ids:
                    await self._stop_camera_processor(camera_id)
            
            # Iniciar/atualizar processadores de câmeras ativas
            for camera in active_cameras:
                if len(self.camera_processors) >= self._max_concurrent_cameras:
                    logger.warning(f"Limite máximo de câmeras ({self._max_concurrent_cameras}) atingido")
                    break
                
                await self._start_or_update_camera_processor(camera, alert_types_dict)
            
            self.stats["cameras_being_processed"] = len(self.camera_processors)
            self.stats["last_check"] = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Erro ao verificar câmeras: {e}")
    
    async def _start_or_update_camera_processor(self, camera: Camera, alert_types: Dict[str, Dict]):
        """Inicia ou atualiza processador de uma câmera"""
        try:
            camera_config = CameraConfig(
                camera_id=camera.id,
                camera_name=camera.name,
                camera_ip=camera.ip_address,
                camera_port=camera.port,
                enabled_alerts=list(alert_types.keys()),  # Por enquanto todos os tipos
                alert_types=alert_types,
                is_active=camera.is_active
            )
            
            if camera.id in self.camera_processors:
                # Atualizar configuração existente
                await self.camera_processors[camera.id].update_config(camera_config)
            else:
                # Criar novo processador
                processor = CameraProcessorFactory.create_processor(camera_config,model_path="models/V11n-ND-V2.pt")
                self.camera_processors[camera.id] = processor
                
                # Iniciar processamento em background
                asyncio.create_task(processor.start_processing())
                logger.info(f"Processador da câmera {camera.name} ({camera.id}) iniciado")
                
        except Exception as e:
            logger.error(f"Erro ao iniciar processador da câmera {camera.id}: {e}")
    
    async def _stop_camera_processor(self, camera_id: int):
        """Para processador de uma câmera"""
        if camera_id in self.camera_processors:
            try:
                await self.camera_processors[camera_id].stop_processing()
                del self.camera_processors[camera_id]
                logger.info(f"Processador da câmera {camera_id} removido")
            except Exception as e:
                logger.error(f"Erro ao parar processador da câmera {camera_id}: {e}")
    
    async def _initialize_handlers(self, handler_configs: Dict[str, Dict[str, Any]]):
        """Inicializa os 4 handlers essenciais"""
        try:
            # 1. Database Handler (sempre ativo - salva alertas no banco)
            self.handlers['database'] = DatabaseHandler()
            await self.handlers['database'].initialize()
            logger.info("✅ DatabaseHandler inicializado")
            
            # 2. MQTT Handler (se configurado)
            if 'mqtt' in handler_configs:
                config = handler_configs['mqtt']
                self.handlers['mqtt'] = MQTTHandler(
                    broker_host=config.get('broker_host', 'localhost'),
                    broker_port=config.get('broker_port', 1883)
                )
                await self.handlers['mqtt'].initialize()
                logger.info("✅ MQTTHandler inicializado")
            
            # 3. AMQP Handler (se configurado)
            if 'amqp' in handler_configs:
                config = handler_configs['amqp']
                self.handlers['amqp'] = AMQPHandler(
                    amqp_url=config.get('amqp_url', 'amqp://guest:guest@localhost:5672/')
                )
                await self.handlers['amqp'].initialize()
                logger.info("✅ AMQPHandler inicializado")
            
            # 4. Frigate Handler (se configurado)
            if 'frigate' in handler_configs:
                config = handler_configs['frigate']
                self.handlers['frigate'] = FrigateHandler(
                    frigate_base_url=config.get('frigate_base_url', 'http://localhost:5000')
                )
                await self.handlers['frigate'].initialize()
                logger.info("✅ FrigateHandler inicializado")
            
            # Registrar handlers no event bus
            # O EventBus espera funções, então registramos os métodos handle_event
            for handler_name, handler in self.handlers.items():
                await event_bus.subscribe(EventType.CAMERA_ALERT_DETECTED, handler.handle_event)
                logger.info(f"🔗 Handler {handler_name} registrado no EventBus")

            videoHandler = NewVideoHandler()
            await videoHandler.initialize()
            logger.info("✅ NewVideoHandler inicializado")
            await event_bus.subscribe(EventType.NEW_VIDEO_FILE, videoHandler.handle_event)
            logger.info("🔗 NewVideoHandler registrado no EventBus")

            detectionHandler = DetectionHandler()
            await detectionHandler.initialize()
            logger.info("✅ DetectionHandler inicializado")
            await event_bus.subscribe(EventType.TRIGGER_DETECTION, detectionHandler.handle_event)
            logger.info("🔗 DetectionHandler registrado no EventBus")
            
            
        except Exception as e:
            logger.error(f"Erro ao inicializar handlers: {e}")
    
    def _update_stats(self):
        """Atualiza estatísticas do sistema"""
        if self.start_time:
            uptime = datetime.utcnow() - self.start_time
            self.stats["uptime_seconds"] = uptime.total_seconds()
        
        # Somar alertas processados de todos os processadores
        total_alerts = sum(
            processor.get_stats().get("alerts_detected", 0)
            for processor in self.camera_processors.values()
        )
        self.stats["total_alerts_processed"] = total_alerts
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do sistema"""
        self._update_stats()
        
        # Estatísticas dos processadores individuais
        camera_processors_stats = []
        for camera_id, processor in self.camera_processors.items():
            camera_processors_stats.append(processor.get_stats())
        
        # Status dos handlers
        handlers_status = {}
        for handler_name, handler in self.handlers.items():
            handlers_status[handler_name] = {
                "active": True,
                "type": handler.__class__.__name__
            }
        
        return {
            **self.stats,
            "camera_processors": camera_processors_stats,
            "handlers_status": handlers_status,
            "is_running": self.is_running
        } 