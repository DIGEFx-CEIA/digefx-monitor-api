"""
Processamento de novos arquivos de vídeo
"""

import asyncio
from datetime import datetime
import logging
from typing import Dict
from .event_system import create_new_video_file_event, event_bus

import cv2


logger = logging.getLogger(__name__)

async def process_new_video(video_path: str):
    """Processa novo arquivo de vídeo"""
    try:
        logger.info(f"Processando novo vídeo: {video_path}")
        
        # Obter informações do vídeo
        video_info = get_video_info(video_path)
        # TODO: validar se o vídeo já foi processado no banco
        # Enviar um evento de novo arquivo de vídeo
        metadata = {
            "video_path": video_path,
            "timestamp": datetime.now().isoformat(),
            "stage": "mediapipe",
            "video_info": video_info
        }
        event = create_new_video_file_event(
            file_path=video_path,
            metadata=metadata
        )
        # Publicar evento
        await event_bus.publish(event)

    except Exception as e:
        logger.error(f"Erro ao processar novo vídeo {video_path}: {e}")


def get_video_info(video_path: str) -> Dict:
    """Extrai informações básicas do vídeo"""
    try:
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise Exception(f"Não foi possível abrir o vídeo: {video_path}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()
        
        return {
            "fps": fps,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter informações do vídeo {video_path}: {e}")
        return {}
        