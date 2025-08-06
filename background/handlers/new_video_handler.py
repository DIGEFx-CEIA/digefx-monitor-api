
import logging
import time
from typing import Dict, Optional

import mediapipe as mp
import cv2
from ..event_system import NewVideoFileEvent
from config import app_config


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
        logger.info("Database Handler finalizado")
    
    async def handle_event(self, event: NewVideoFileEvent) -> bool:
        """Processa evento de novo arquivo de vídeo"""
        try:
            logger.info(f"Novo arquivo de vídeo recebido: {event.file_path} às {event.timestamp}")

            # TODO: Verificar se já foi processado
            start_time = time.time()
            
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
                detection = self.detect_person_in_frame(frame, timestamp)
                
                if detection:
                    detections.append(detection)
                    logger.debug(f"Pessoa detectada no frame {frame_count} (t={timestamp:.2f}s)")
                
                frame_count += 1            
            cap.release()
            
            processing_time = time.time() - start_time
            logger.info(f"Processamento concluído: {len(detections)} detecções em {processing_time:.2f}s")
            
            if detections:
                event.metadata['detections'] = detections
                # TODO: publish detections to event bus
            return True
        
        except Exception as e:
            self.logger.error(f"Erro ao processar vídeo {event.file_path}: {e}")
            return False
        
        
    def detect_person_in_frame(self, frame, timestamp: float) -> Optional[Dict]:
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
            self.logger.error(f"Erro ao detectar pessoa no frame: {e}")
            return None