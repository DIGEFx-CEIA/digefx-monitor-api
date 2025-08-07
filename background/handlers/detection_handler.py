import logging
from ..event_system import TriggerDetectionEvent


logger = logging.getLogger(__name__)

class DetectionHandler:
    def __init__(self):
        self.is_initialized = False

    async def initialize(self):
        """Inicializa o handler de detecção"""
        self.is_initialized = True
        logger.info("Detection Handler inicializado")

    async def cleanup(self):
        """Limpa recursos do handler"""
        logger.info("Detection Handler finalizado")

    async def handle_event(self, event: TriggerDetectionEvent) -> bool:
        """Processa evento de novo arquivo de vídeo"""
        try:
            logger.info(f"Evento de detecção recebido para a camera: {event.camera.name} às {event.timestamp}")
            # Verificar se a câmera está ativa
            if not event.camera or not event.camera.is_active:
                logger.info(f"Câmera {event.camera.name} não está ativa. Evento ignorado.")
                return False
            logger.info(f"Alertas habilitados: {event.camera.enabled_alerts}")

        except Exception as e:
            logger.error(f"Erro ao processar evento de detecção: {e}")
            return False