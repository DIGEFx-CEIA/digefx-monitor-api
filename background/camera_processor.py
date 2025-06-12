"""
Processador individual de câmera - Interface para caixa preta de inferência
Este módulo define a interface que será implementada pela lógica de processamento de imagens
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import time
import random

from .event_system import event_bus, create_alert_event, EventType

logger = logging.getLogger(__name__)

@dataclass
class CameraConfig:
    """Configuração de uma câmera para processamento"""
    camera_id: int
    camera_name: str
    camera_ip: str
    camera_port: int
    enabled_alerts: List[str]  # Lista de códigos de tipos de alerta
    alert_types: Dict[str, Dict[str, Any]]  # Cache dos tipos de alerta
    is_active: bool = True

class CameraProcessor:
    """
    Processador individual de câmera
    
    Esta é a interface que será implementada pela caixa preta de inferência.
    Por enquanto contém stubs que simulam o processamento real.
    """
    
    def __init__(self, camera_config: CameraConfig):
        self.config = camera_config
        self.is_running = False
        self.last_frame_time = None
        self.processing_stats = {
            "frames_processed": 0,
            "alerts_detected": 0,
            "processing_time_avg": 0.0,
            "last_alert_time": None,
            "start_time": None
        }
        self._stop_event = asyncio.Event()
        
    async def start_processing(self):
        """Inicia o processamento da câmera"""
        if self.is_running:
            logger.warning(f"Processamento da câmera {self.config.camera_id} já está ativo")
            return
            
        self.is_running = True
        self._stop_event.clear()
        self.processing_stats["start_time"] = datetime.utcnow()
        
        logger.info(f"Iniciando processamento da câmera {self.config.camera_name} ({self.config.camera_id})")
        
        try:
            await self._processing_loop()
        except Exception as e:
            logger.error(f"Erro no processamento da câmera {self.config.camera_id}: {e}")
        finally:
            self.is_running = False
            logger.info(f"Processamento da câmera {self.config.camera_name} finalizado")
    
    async def stop_processing(self):
        """Para o processamento da câmera"""
        if not self.is_running:
            return
            
        logger.info(f"Parando processamento da câmera {self.config.camera_name}")
        self._stop_event.set()
        
        # Aguardar o processamento parar (timeout de 5 segundos)
        for _ in range(50):  # 5 segundos
            if not self.is_running:
                break
            await asyncio.sleep(0.1)
        
        if self.is_running:
            logger.warning(f"Timeout ao parar processamento da câmera {self.config.camera_id}")
    
    async def update_config(self, new_config: CameraConfig):
        """Atualiza configuração da câmera"""
        logger.info(f"Atualizando configuração da câmera {self.config.camera_id}")
        self.config = new_config
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do processamento"""
        stats = self.processing_stats.copy()
        stats["is_running"] = self.is_running
        stats["camera_id"] = self.config.camera_id
        stats["camera_name"] = self.config.camera_name
        stats["last_alert_time"] = stats["last_alert_time"].isoformat() if stats["last_alert_time"] else None
        if stats["start_time"]:
            uptime = (datetime.utcnow() - stats["start_time"])
            stats["uptime_seconds"] = uptime.total_seconds()
        stats["start_time"] = stats["start_time"].isoformat() if stats["start_time"] else None
        
        return stats
    
    async def _processing_loop(self):
        """
        Loop principal de processamento
        
        STUB: Esta função será substituída pela implementação real
        que fará a captura de frames e inferência de IA
        """
        frame_interval = 1.0 / 30.0  # 30 FPS
        
        while not self._stop_event.is_set() and self.config.is_active:
            try:
                start_time = time.time()
                
                # STUB: Simular captura de frame
                frame_data = await self._capture_frame()
                
                if frame_data:
                    # STUB: Simular processamento de inferência
                    detections = await self._process_frame(frame_data)
                    
                    # Processar detecções
                    for detection in detections:
                        await self._handle_detection(detection)
                    
                    self.processing_stats["frames_processed"] += 1
                
                # Calcular tempo de processamento
                processing_time = time.time() - start_time
                self._update_processing_stats(processing_time)
                
                # Aguardar próximo frame
                sleep_time = max(0, frame_interval - processing_time)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Erro no loop de processamento da câmera {self.config.camera_id}: {e}")
                await asyncio.sleep(1.0)  # Aguardar antes de tentar novamente
    
    async def _capture_frame(self) -> Optional[Dict[str, Any]]:
        """
        STUB: Captura um frame da câmera
        
        Implementação real deve:
        - Conectar com a câmera via RTSP/HTTP
        - Capturar frame atual
        - Retornar dados do frame ou None se erro
        """
        # Simular tempo de captura
        await asyncio.sleep(0.01)
        
        # Simular falha ocasional de captura
        if random.random() < 0.05:  # 5% de chance de falha
            return None
        
        # Simular dados do frame
        return {
            "timestamp": datetime.utcnow(),
            "frame_id": self.processing_stats["frames_processed"],
            "width": 1920,
            "height": 1080,
            "format": "jpg",
            "data": b"fake_frame_data"  # Em implementação real seria os bytes da imagem
        }
    
    async def _process_frame(self, frame_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        STUB: Processa frame com IA para detectar objetos/eventos
        
        Implementação real deve:
        - Executar modelo de IA no frame
        - Retornar lista de detecções com confiança
        - Filtrar por threshold de confiança
        """
        # Simular tempo de inferência
        await asyncio.sleep(0.05)  # 50ms de inferência
        
        detections = []
        
        # Simular detecções ocasionais
        for alert_code in self.config.enabled_alerts:
            # Probabilidade baixa de detecção para cada tipo
            if random.random() < 0.01:  # 1% de chance por frame
                alert_type = self.config.alert_types.get(alert_code, {})
                
                detection = {
                    "alert_code": alert_code,
                    "alert_type": alert_type,
                    "confidence": random.uniform(0.7, 0.95),
                    "bbox": {
                        "x": random.randint(0, 1800),
                        "y": random.randint(0, 980),
                        "width": random.randint(50, 200),
                        "height": random.randint(50, 200)
                    },
                    "frame_data": frame_data,
                    "detected_at": datetime.utcnow()
                }
                detections.append(detection)
        
        return detections
    
    async def _handle_detection(self, detection: Dict[str, Any]):
        """Processa uma detecção e gera evento de alerta"""
        alert_type = detection["alert_type"]
        
        if not alert_type:
            logger.warning(f"Tipo de alerta não encontrado para código {detection['alert_code']}")
            return
        
        # Criar evento de alerta
        event = create_alert_event(
            camera_id=self.config.camera_id,
            camera_name=self.config.camera_name,
            camera_ip=self.config.camera_ip,
            alert_type_code=detection["alert_code"],
            alert_type_name=alert_type.get("name", "Unknown"),
            alert_type_id=alert_type.get("id", 0),
            severity=alert_type.get("severity", "medium"),
            confidence=detection["confidence"],
            metadata={
                "bbox": detection["bbox"],
                "frame_id": detection["frame_data"]["frame_id"],
                "camera_resolution": {
                    "width": detection["frame_data"]["width"],
                    "height": detection["frame_data"]["height"]
                },
                "processing_stats": self.get_stats()
            },
            image_path=f"/tmp/alerts/camera_{self.config.camera_id}_frame_{detection['frame_data']['frame_id']}.jpg",
            video_clip_path=f"/tmp/alerts/camera_{self.config.camera_id}_clip_{int(time.time())}.mp4"
        )
        
        # Publicar evento
        await event_bus.publish(event)
        
        # Atualizar estatísticas
        self.processing_stats["alerts_detected"] += 1
        self.processing_stats["last_alert_time"] = datetime.utcnow()
        
        logger.info(f"Alerta detectado: {detection['alert_code']} na câmera {self.config.camera_name} "
                   f"(confiança: {detection['confidence']:.2f})")
    
    def _update_processing_stats(self, processing_time: float):
        """Atualiza estatísticas de processamento"""
        # Média móvel do tempo de processamento
        if self.processing_stats["processing_time_avg"] == 0:
            self.processing_stats["processing_time_avg"] = processing_time
        else:
            alpha = 0.1  # Fator de suavização
            self.processing_stats["processing_time_avg"] = (
                alpha * processing_time + 
                (1 - alpha) * self.processing_stats["processing_time_avg"]
            )
        
        self.last_frame_time = datetime.utcnow()

class CameraProcessorFactory:
    """Factory para criar processadores de câmera"""
    
    @staticmethod
    def create_processor(camera_config: CameraConfig) -> CameraProcessor:
        """Cria um novo processador para a câmera"""
        return CameraProcessor(camera_config) 