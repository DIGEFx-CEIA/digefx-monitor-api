"""
Handler Database - Salva alertas no banco de dados quando são detectados
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from ..event_system import AlertEvent, EventType
from models import Camera, CameraAlert, AlertType
from config import get_db_session

logger = logging.getLogger(__name__)

class DatabaseHandler:
    """Handler para salvar alertas no banco de dados"""
    
    def __init__(self):
        self.is_initialized = False
        
    async def initialize(self):
        """Inicializa o handler do banco de dados"""
        try:
            # Testar conexão com o banco
            with get_db_session() as db:
                # Testar query simples
                cameras = db.query(Camera).limit(1).all()
                self.is_initialized = True
                logger.info("Database Handler inicializado")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar Database Handler: {e}")
            raise
    
    async def cleanup(self):
        """Limpa recursos do handler"""
        logger.info("Database Handler finalizado")
    
    async def handle_event(self, event: AlertEvent) -> bool:
        """Processa evento de alerta salvando no banco de dados"""
        try:
            with get_db_session() as db:
                try:
                    # Validar se a câmera existe
                    camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
                    if not camera:
                        logger.warning(f"Câmera {event.camera_id} não encontrada no banco")
                        return False
                    
                    # Validar se o tipo de alerta existe
                    alert_type = db.query(AlertType).filter(AlertType.id == event.alert_type_id).first()
                    if not alert_type:
                        logger.warning(f"Tipo de alerta {event.alert_type_id} não encontrado no banco")
                        return False
                    
                    # Criar registro de alerta
                    camera_alert = CameraAlert(
                        camera_id=event.camera_id,
                        alert_type_id=event.alert_type_id,
                        triggered_at=event.detected_at,
                        # corrige conversão do Dict para Json quando tem datetime dentro do dicionário
                        alert_metadata=event.metadata
                    )
                    
                    # Salvar no banco
                    db.add(camera_alert)
                    db.commit()
                    db.refresh(camera_alert)
                    
                    logger.info(f"Alerta salvo no banco - ID: {camera_alert.id}, "
                              f"Câmera: {event.camera_name}, Tipo: {event.alert_type_code}")
                    
                    # Atualizar estatísticas da câmera (opcional)
                    self._update_camera_stats(db, camera, event)
                    
                    return True
                    
                except Exception as e:
                    db.rollback()
                    logger.error(f"Erro ao salvar alerta no banco: {e}")
                    return False
                
        except Exception as e:
            logger.error(f"Erro geral no Database Handler: {e}")
            return False
    
    def _prepare_alert_data(self, event: AlertEvent, camera: Camera, alert_type: AlertType) -> Dict[str, Any]:
        """Prepara dados do alerta para inserção no banco"""
        return {
            "camera_id": camera.id,
            "alert_type_id": alert_type.id,
            "triggered_at": event.detected_at,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "image_path": event.image_path,
            "video_clip_path": event.video_clip_path,
            "confidence": event.confidence,
            "metadata": {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "camera_ip": event.camera_ip,
                "severity": event.severity,
                "processing_metadata": event.metadata
            }
        }
    
    def _update_camera_stats(self, db, camera: Camera, event: AlertEvent):
        """Atualiza estatísticas da câmera (opcional)"""
        try:
            # Calcular estatísticas simples
            total_alerts = db.query(CameraAlert).filter(CameraAlert.camera_id == camera.id).count()
            resolved_alerts = db.query(CameraAlert).filter(
                CameraAlert.camera_id == camera.id,
                CameraAlert.resolved == True
            ).count()
            
            # Atualizar metadata da câmera com estatísticas
            current_metadata = camera.metadata or {}
            current_metadata.update({
                "alert_stats": {
                    "total_alerts": total_alerts,
                    "resolved_alerts": resolved_alerts,
                    "pending_alerts": total_alerts - resolved_alerts,
                    "last_alert_at": datetime.utcnow().isoformat(),
                    "last_alert_type": event.alert_type_code
                },
                "updated_at": datetime.utcnow().isoformat()
            })
            
            # Atualizar no banco
            camera.metadata = current_metadata
            db.commit()
            
            logger.debug(f"Estatísticas da câmera {camera.id} atualizadas")
            
        except Exception as e:
            logger.error(f"Erro ao atualizar estatísticas da câmera {camera.id}: {e}")
            # Não falhar o handler por erro nas estatísticas
            pass 