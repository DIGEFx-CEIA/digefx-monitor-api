"""
Handler Frigate - Integra com API do Frigate quando alertas são detectados
"""
import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urljoin

from ..event_system import AlertEvent, EventType

logger = logging.getLogger(__name__)

class FrigateHandler:
    """Handler para integração com API do Frigate"""
    
    def __init__(self,
                 frigate_base_url: str = "http://localhost:5000",
                 api_timeout: int = 30,
                 max_retries: int = 3):
        self.frigate_base_url = frigate_base_url.rstrip('/')
        self.api_timeout = api_timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_initialized = False
        
    async def initialize(self):
        """Inicializa o handler do Frigate"""
        try:
            # Criar sessão HTTP
            timeout = aiohttp.ClientTimeout(total=self.api_timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "DIGEFx-Monitor/1.0"
                }
            )
            
            # Testar conectividade com Frigate
            await self._test_frigate_connection()
            
            self.is_initialized = True
            logger.info(f"Frigate Handler inicializado - URL: {self.frigate_base_url}")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar Frigate Handler: {e}")
            if self.session:
                await self.session.close()
            raise
    
    async def cleanup(self):
        """Limpa recursos do handler"""
        if self.session:
            await self.session.close()
        logger.info("Frigate Handler finalizado")
    
    async def handle_event(self, event: AlertEvent) -> bool:
        """Processa evento de alerta enviando para API do Frigate"""
        if not self.is_initialized or not self.session:
            logger.error("Frigate Handler não inicializado")
            return False
        
        success = False
        
        # Tentar múltiplas operações com Frigate
        tasks = [
            self._register_event(event),
            self._update_camera_config(event),
            self._save_detection_data(event)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verificar se pelo menos uma operação foi bem-sucedida
        for result in results:
            if isinstance(result, bool) and result:
                success = True
                break
        
        if not success:
            logger.warning(f"Nenhuma operação Frigate foi bem-sucedida para evento {event.event_id}")
        
        return success
    
    async def _test_frigate_connection(self):
        """Testa conectividade com API do Frigate"""
        try:
            url = urljoin(self.frigate_base_url, "/api/stats")
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Frigate conectado - Versão: {data.get('version', 'unknown')}")
                else:
                    raise Exception(f"Frigate API retornou status {response.status}")
                    
        except Exception as e:
            logger.error(f"Falha ao conectar com Frigate: {e}")
            raise
    
    async def _register_event(self, event: AlertEvent) -> bool:
        """Registra evento de alerta no Frigate"""
        try:
            url = urljoin(self.frigate_base_url, "/api/events")
            
            # Preparar dados do evento
            event_data = {
                "id": event.event_id,
                "camera": f"camera_{event.camera_id}",
                "label": event.alert_type_code,
                "top_score": event.confidence,
                "start_time": event.detected_at.timestamp(),
                "end_time": event.detected_at.timestamp(),
                "has_clip": bool(event.video_clip_path),
                "has_snapshot": bool(event.image_path),
                "zones": [],
                "thumbnail": event.image_path,
                "data": {
                    "box": event.metadata.get("bbox", {}),
                    "region": event.metadata.get("region", {}),
                    "score": event.confidence,
                    "type": "object"
                }
            }
            
            # Enviar para Frigate
            for attempt in range(self.max_retries):
                try:
                    async with self.session.post(url, json=event_data) as response:
                        if response.status in [200, 201]:
                            logger.info(f"Evento registrado no Frigate: {event.event_id}")
                            return True
                        else:
                            error_text = await response.text()
                            logger.warning(f"Frigate event registration failed (attempt {attempt + 1}): "
                                         f"Status {response.status} - {error_text}")
                            
                except Exception as e:
                    logger.warning(f"Erro ao registrar evento no Frigate (attempt {attempt + 1}): {e}")
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao registrar evento no Frigate: {e}")
            return False
    
    async def _update_camera_config(self, event: AlertEvent) -> bool:
        """Atualiza configuração da câmera no Frigate"""
        try:
            camera_name = f"camera_{event.camera_id}"
            url = urljoin(self.frigate_base_url, f"/api/config/cameras/{camera_name}")
            
            # Buscar configuração atual
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"Câmera {camera_name} não encontrada no Frigate")
                    return False
                
                current_config = await response.json()
            
            # Atualizar estatísticas na configuração
            if "metadata" not in current_config:
                current_config["metadata"] = {}
            
            current_config["metadata"].update({
                "last_alert": {
                    "timestamp": event.detected_at.isoformat(),
                    "type": event.alert_type_code,
                    "confidence": event.confidence,
                    "event_id": event.event_id
                },
                "alert_stats": current_config["metadata"].get("alert_stats", {})
            })
            
            # Incrementar contador do tipo de alerta
            alert_stats = current_config["metadata"]["alert_stats"]
            if event.alert_type_code not in alert_stats:
                alert_stats[event.alert_type_code] = 0
            alert_stats[event.alert_type_code] += 1
            
            # Enviar configuração atualizada
            async with self.session.put(url, json=current_config) as response:
                if response.status == 200:
                    logger.debug(f"Configuração da câmera {camera_name} atualizada no Frigate")
                    return True
                else:
                    logger.warning(f"Falha ao atualizar configuração no Frigate: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao atualizar configuração da câmera no Frigate: {e}")
            return False
    
    async def _save_detection_data(self, event: AlertEvent) -> bool:
        """Salva dados de detecção no Frigate"""
        try:
            url = urljoin(self.frigate_base_url, "/api/detections")
            
            # Preparar dados de detecção
            detection_data = {
                "event_id": event.event_id,
                "camera_id": event.camera_id,
                "camera_name": event.camera_name,
                "timestamp": event.triggered_at.isoformat(),
                "detection": {
                    "label": event.alert_type_code,
                    "confidence": event.confidence,
                    "box": event.metadata.get("bbox", {}),
                    "area": self._calculate_detection_area(event.metadata.get("bbox", {})),
                    "ratio": self._calculate_detection_ratio(event.metadata.get("bbox", {})),
                    "region": event.metadata.get("region", {})
                },
                "image": {
                    "path": event.image_path,
                    "width": event.metadata.get("camera_resolution", {}).get("width", 0),
                    "height": event.metadata.get("camera_resolution", {}).get("height", 0)
                },
                "video": {
                    "path": event.video_clip_path,
                    "duration": 10.0  # Duração padrão do clipe
                },
                "metadata": {
                    "severity": event.severity,
                    "processing_stats": event.metadata.get("processing_stats", {}),
                    "source": "digefx-monitor"
                }
            }
            
            # Enviar dados de detecção
            async with self.session.post(url, json=detection_data) as response:
                if response.status in [200, 201]:
                    logger.debug(f"Dados de detecção salvos no Frigate: {event.event_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.warning(f"Falha ao salvar detecção no Frigate: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao salvar detecção no Frigate: {e}")
            return False
    
    def _calculate_detection_area(self, bbox: Dict[str, Any]) -> float:
        """Calcula área da detecção"""
        try:
            width = bbox.get("width", 0)
            height = bbox.get("height", 0)
            return float(width * height)
        except:
            return 0.0
    
    def _calculate_detection_ratio(self, bbox: Dict[str, Any]) -> float:
        """Calcula ratio da detecção"""
        try:
            width = bbox.get("width", 0)
            height = bbox.get("height", 0)
            if height > 0:
                return float(width / height)
            return 0.0
        except:
            return 0.0

def create_frigate_handler(**kwargs) -> FrigateHandler:
    """Factory function para criar handler Frigate"""
    return FrigateHandler(**kwargs) 