
import logging
import time
import os
from typing import Dict, Optional

import mediapipe as mp
import cv2
from ..event_system import NewVideoFileEvent, create_trigger_detection_event, event_bus
from config import app_config, get_db_session
from models import Camera


logger = logging.getLogger(__name__)

class NewVideoHandler:
    """Handler para processar novos arquivos de vídeo"""
        
    def __init__(self):
        self.is_initialized = False
        # Configurar MediaPipe
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=app_config.MEDIAPIPE_CONFIDENCE,
            min_tracking_confidence=0.5
        )
        
    async def initialize(self):
        self.is_initialized = True
    
    async def cleanup(self):
        """Limpa recursos do handler"""
        logger.info("Video Handler finalizado")

    def wait_for_file_complete(self, file_path: str, max_wait: int = 30) -> bool:
        """Aguarda arquivo estar completamente escrito"""
        start_time = time.time()
        last_size = 0
        
        while time.time() - start_time < max_wait:
            if not os.path.exists(file_path):
                time.sleep(1)
                continue
                
            current_size = os.path.getsize(file_path)
            if current_size > 0 and current_size == last_size:
                # Arquivo parou de crescer, assumir que está completo
                time.sleep(2)  # Aguardar mais 2 segundos para garantir
                return True
                
            last_size = current_size
            time.sleep(1)
        
        return False
    
    async def handle_event(self, event: NewVideoFileEvent) -> bool:
        """Processa evento de novo arquivo de vídeo"""
        try:
            logger.info(f"Novo arquivo de vídeo recebido: {event.file_path} às {event.timestamp}")
            # verificar se existe camera ativa cadastrada com esse nome
            with get_db_session() as db:
                camera_name = event.file_path.split("/")[-2] if "/" in event.file_path else "unknown_camera"
                existent_camera = db.query(Camera).filter(Camera.name == camera_name, Camera.is_active == True).first()
                if not existent_camera:
                    logger.info(f"Câmera {camera_name} não encontrada no banco de dados. Evento ignorado.")
                    return False
                logger.info(f"Câmera {existent_camera.name} encontrada no banco de dados. Processando vídeo...")
                event.camera = existent_camera

            # TODO: Verificar se já foi processado
            start_time = time.time()
            
            if not self.wait_for_file_complete(event.file_path):
                logger.error(f"Arquivo não ficou completo: {event.file_path}")
                return False
            
            cap = cv2.VideoCapture(event.file_path)
            
            if not cap.isOpened():
                raise Exception(f"Não foi possível abrir o vídeo: {event.file_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            detections = []
            frame_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Calcular timestamp do frame
                timestamp = frame_count / fps
                
                # Detectar pessoa no frame
                detection = self.detect_person_in_frame(frame, timestamp, frame_count=frame_count)
                
                if detection:
                    detections.append(detection)
                    logger.debug(f"Pessoa detectada no frame {frame_count} (t={timestamp:.2f}s)")
                
                frame_count += 1            
            cap.release()
            
            processing_time = time.time() - start_time
            logger.info(f"Processamento concluído: {len(detections)} detecções em {processing_time:.2f}s")
            
            #dispara evento se houver detecções em 10% dos frames
            if len(detections) / frame_count >= 0.1:
                event.metadata['detections'] = detections
                logger.info(f"🔍 Disparando evento de detecção para {event.file_path} com {len(detections)} detecções")
                trigger_event = create_trigger_detection_event(event)
                await event_bus.publish(trigger_event)
            else:
                logger.info(f"🔍 Nenhuma detecção significativa de pessoa em {event.file_path}. Evento não disparado.")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao processar vídeo {event.file_path}: {e}")
            return False
        
        
    def detect_person_in_frame(self, frame, timestamp: float, frame_count: int) -> Optional[Dict]:
        """Detecta pessoa em um frame usando MediaPipe"""
        try:
            # Converter BGR para RGB (MediaPipe usa RGB)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Processar frame
            results = self.pose.process(rgb_frame)
            
            if results.pose_landmarks:
                # Calcular confiança média dos landmarks
                confidence = sum([landmark.visibility for landmark in results.pose_landmarks.landmark]) / len(results.pose_landmarks.landmark)
                
                # Obter bounding box dos landmarks
                landmarks = results.pose_landmarks.landmark
                x_coords = [landmark.x for landmark in landmarks]
                y_coords = [landmark.y for landmark in landmarks]
                
                min_x = min(x_coords)
                max_x = max(x_coords)
                min_y = min(y_coords)
                max_y = max(y_coords)
                
                return {
                    "timestamp": timestamp,
                    "frame_count": frame_count,
                    "confidence": confidence,
                    "bounding_box": {
                        "min_x": min_x,
                        "max_x": max_x,
                        "min_y": min_y,
                        "max_y": max_y
                    },
                    "landmarks_count": len(landmarks)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Erro ao detectar pessoa no frame: {e}")
            return None