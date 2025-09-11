import logging
import time
import asyncio
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import cv2
import numpy as np
from ultralytics import YOLO
from ..event_system import TriggerDetectionEvent, event_bus, create_alert_event
from config import app_config
from models import SessionLocal, CameraAlert


logger = logging.getLogger(__name__)

class DetectionHandler:
    def __init__(self):
        self.is_initialized = False
        # Configurações de processamento paralelo vindas do app_config
        self.max_workers = app_config.DETECTION_MAX_WORKERS
        self.alert_cooldown_hours = app_config.ALERT_COOLDOWN_HOURS
        self.detection_threshold = app_config.DETECTION_THRESHOLD_PERCENT
        
        try:
            logger.info(f"Carregando modelo YOLO: {app_config.YOLO_MODEL}")
            self.model = YOLO(app_config.YOLO_MODEL)
            logger.info("Modelo YOLO carregado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao carregar modelo YOLO: {e}")
            raise

    async def initialize(self):
        """Inicializa o handler de detecção"""
        self.is_initialized = True
        logger.info("Detection Handler inicializado")

    async def cleanup(self):
        """Limpa recursos do handler"""
        logger.info("Detection Handler finalizado")

    async def handle_event(self, event: TriggerDetectionEvent) -> bool:
        """Processa evento de detecção com processamento paralelo"""
        try:
            logger.info(f"Evento de detecção recebido para a camera: {event.camera.name} às {event.timestamp}")
            
            # Verificar se a câmera está ativa
            if not event.camera or not event.camera.is_active:
                logger.info(f"Câmera {event.camera.name} não está ativa. Evento ignorado.")
                return False
                
            logger.info(f"Alertas habilitados: {event.camera.enabled_alerts}")
            
            # Processar vídeo com YOLO de forma paralela
            alert_counts = await self.process_video_parallel(event)
            
            # Gerar alertas baseado nos resultados
            await self.generate_alerts_from_counts(event, alert_counts)
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao processar evento de detecção: {e}")
            return False
        
    async def process_video_parallel(self, event: TriggerDetectionEvent) -> Dict[str, int]:
        """Processa vídeo de forma paralela usando múltiplos cores"""
        try:
            logger.info(f"Iniciando processamento YOLO paralelo: {event.file_path}")
            start_time = time.time()
            
            # Obter detecções do MediaPipe do evento
            mediapipe_detections = event.metadata.get('detections', [])
            if not mediapipe_detections:
                logger.warning("Nenhuma detecção do MediaPipe encontrada no evento")
                return {}
            
            # Extrair timestamps onde MediaPipe detectou pessoa
            detection_timestamps = {detection["timestamp"] for detection in mediapipe_detections}
            logger.info(f"Processando {len(detection_timestamps)} timestamps com detecção de pessoa")
            
            # Abrir vídeo para obter informações
            cap = cv2.VideoCapture(event.file_path)
            if not cap.isOpened():
                raise Exception(f"Não foi possível abrir o vídeo: {event.file_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            
            # Preparar tarefas de processamento paralelo
            frame_indices = []
            
            for frame_idx in range(total_frames):
                timestamp = frame_idx / fps
                # Processar apenas frames onde MediaPipe detectou pessoa (±1 segundo)
                if any(abs(timestamp - det_time) <= 1.0 for det_time in detection_timestamps):
                    frame_indices.append(frame_idx)
            
            logger.info(f"Processando {len(frame_indices)} frames de {total_frames} total ({len(frame_indices)/total_frames*100:.1f}%)")
            
            # Dividir frames em lotes para processamento paralelo
            batch_size = max(1, len(frame_indices) // self.max_workers)
            batches = [frame_indices[i:i + batch_size] for i in range(0, len(frame_indices), batch_size)]
            
            # Executar processamento paralelo
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    loop.run_in_executor(
                        executor, 
                        self.process_frame_batch, 
                        event.file_path, 
                        batch, 
                        fps,
                        event.camera.enabled_alerts
                    ) 
                    for batch in batches
                ]
                
                # Aguardar todos os lotes terminarem
                batch_results = await asyncio.gather(*futures)
            
            # Consolidar resultados
            alert_counts = {}
            total_processed_frames = 0
            
            for batch_result in batch_results:
                total_processed_frames += batch_result["frames_processed"]
                for alert_type, count in batch_result["alert_counts"].items():
                    alert_counts[alert_type] = alert_counts.get(alert_type, 0) + count
            
            processing_time = time.time() - start_time
            logger.info(f"Processamento YOLO paralelo concluído: {total_processed_frames} frames em {processing_time:.2f}s")
            logger.info(f"Contagens de alertas: {alert_counts}")
            
            # Adicionar informações de contexto
            alert_counts["_metadata"] = {
                "total_processed_frames": total_processed_frames,
                "processing_time": processing_time,
                "fps": fps
            }
            
            return alert_counts
            
        except Exception as e:
            logger.error(f"Erro ao processar vídeo paralelo {event.file_path}: {e}")
            return {}
    
    def process_frame_batch(self, video_path: str, frame_indices: List[int], fps: float, enabled_alerts: List[str]) -> Dict:
        """Processa um lote de frames de forma síncrona (executado em thread separada)"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"Erro ao abrir vídeo para processamento de lote: {video_path}")
                return {"frames_processed": 0, "alert_counts": {}}
            
            alert_counts = {}
            frames_processed = 0
            monitored_classes = set(enabled_alerts)
            
            for frame_idx in frame_indices:
                # Ir para o frame específico
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    continue
                
                timestamp = frame_idx / fps
                
                # Executar YOLO no frame
                detections = self.detect_objects_in_frame(frame, timestamp)
                
                # Processar detecções seguindo a lógica do camera_processor
                detected_classes = set()
                for detection in detections:
                    class_name = detection.get("class_name", "")
                    # Usar diretamente as classes do modelo (já em português)
                    if class_name in monitored_classes:
                        detected_classes.add(class_name)
                
                # Aplicar regras de negócio similar ao _yolo_inference_loop
                # Modelo retorna classes em MAIÚSCULAS: PESSOA, COM_CAPACETE, COM_LUVA, etc.
                # Banco tem códigos em inglês: NO_HELMET, SMOKING, etc.
                
                if "PESSOA" in detected_classes:
                    # Se detectou pessoa mas não detectou capacete → NO_HELMET
                    if "COM_CAPACETE" not in detected_classes:
                        alert_counts["NO_HELMET"] = alert_counts.get("NO_HELMET", 0) + 1
                    
                    # Se detectou pessoa mas não detectou luva → NO_GLOVES  
                    if "COM_LUVA" not in detected_classes:
                        alert_counts["NO_GLOVES"] = alert_counts.get("NO_GLOVES", 0) + 1
                
                # Adversidades diretas - mapear classes do modelo para códigos do banco
                class_to_alert_mapping = {
                    "FUMANDO_CIGARRO": "SMOKING",
                    "SEM_CINTO": "NO_SEAT_BELT", 
                    "USANDO_CELULAR": "USING_CELL_PHONE"
                }
                
                for model_class, alert_code in class_to_alert_mapping.items():
                    if model_class in detected_classes:
                        alert_counts[alert_code] = alert_counts.get(alert_code, 0) + 1
                
                frames_processed += 1
            
            cap.release()
            return {"frames_processed": frames_processed, "alert_counts": alert_counts}
            
        except Exception as e:
            logger.error(f"Erro ao processar lote de frames: {e}")
            return {"frames_processed": 0, "alert_counts": {}}
    
    async def generate_alerts_from_counts(self, event: TriggerDetectionEvent, alert_counts: Dict[str, int]):
        """Gera alertas baseado nas contagens e cooldown"""
        try:
            metadata = alert_counts.get("_metadata", {})
            total_frames = metadata.get("total_processed_frames", 0)
            
            if total_frames == 0:
                logger.warning("Nenhum frame processado, não gerando alertas")
                return
            
            for alert_type, count in alert_counts.items():
                if alert_type.startswith("_"):  # Skip metadata
                    continue
                
                # Verificar se atingiu o threshold (10% dos frames)
                percentage = count / total_frames
                if percentage >= self.detection_threshold:
                    logger.info(f"Alerta {alert_type}: {count}/{total_frames} frames ({percentage*100:.1f}%)")
                    
                    # Verificar cooldown
                    if await self.should_trigger_alert(event.camera.id, alert_type):
                        await self.create_and_publish_alert(event, alert_type, count, total_frames, percentage)
                    else:
                        logger.info(f"Alerta {alert_type} em cooldown para câmera {event.camera.name}")
                else:
                    logger.debug(f"Alerta {alert_type} abaixo do threshold: {percentage*100:.1f}% < {self.detection_threshold*100}%")
        
        except Exception as e:
            logger.error(f"Erro ao gerar alertas: {e}")
    
    async def should_trigger_alert(self, camera_id: int, alert_type: str) -> bool:
        """Verifica cooldown de alertas"""
        try:
            db = SessionLocal()
            
            # Buscar último alerta deste tipo para esta câmera
            cutoff_time = datetime.utcnow() - timedelta(hours=self.alert_cooldown_hours)
            
            recent_alert = db.query(CameraAlert).filter(
                CameraAlert.camera_id == camera_id,
                CameraAlert.triggered_at > cutoff_time
            ).join(CameraAlert.alert_type).filter(
                CameraAlert.alert_type.has(code=alert_type)
            ).first()
            
            db.close()
            
            should_trigger = recent_alert is None
            if not should_trigger:
                logger.debug(f"Alerta {alert_type} em cooldown até {recent_alert.triggered_at + timedelta(hours=self.alert_cooldown_hours)}")
            
            return should_trigger
            
        except Exception as e:
            logger.error(f"Erro ao verificar cooldown: {e}")
            return False
    
    async def create_and_publish_alert(self, event: TriggerDetectionEvent, alert_type: str, count: int, total_frames: int, percentage: float):
        """Cria e publica alerta no event bus"""
        try:
            # Buscar informações do tipo de alerta
            from models import AlertType
            db = SessionLocal()
            
            alert_type_obj = db.query(AlertType).filter(AlertType.code == alert_type).first()
            if not alert_type_obj:
                logger.warning(f"Tipo de alerta {alert_type} não encontrado no banco")
                db.close()
                return
            
            # Criar evento de alerta
            alert_event = create_alert_event(
                camera_id=event.camera.id,
                camera_name=event.camera.name,
                camera_ip=event.camera.ip_address,
                alert_type_code=alert_type,
                alert_type_name=alert_type_obj.name,
                alert_type_id=alert_type_obj.id,
                severity=alert_type_obj.severity,
                confidence=percentage,  # Usar percentual como confiança
                metadata={
                    "video_file": event.file_path,
                    "detection_count": count,
                    "total_frames": total_frames,
                    "detection_percentage": percentage,
                    "processing_timestamp": event.timestamp.isoformat(),
                    "cooldown_hours": self.alert_cooldown_hours
                }
            )
            
            # Publicar no event bus
            await event_bus.publish(alert_event)
            
            logger.info(f"Alerta {alert_type} publicado para câmera {event.camera.name} - {count}/{total_frames} frames ({percentage*100:.1f}%)")
            
            db.close()
            
        except Exception as e:
            logger.error(f"Erro ao criar e publicar alerta: {e}")
        
    def detect_objects_in_frame(self, frame, timestamp: float) -> List[Dict]:
        """Detecta objetos em um frame usando YOLO"""
        try:
            # Fazer detecção
            results = self.model(frame, conf=app_config.YOLO_CONFIDENCE, verbose=False)
            
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # Obter informações da detecção
                        class_id = int(box.cls.cpu().numpy())
                        confidence = float(box.conf.cpu().numpy())
                        class_name = self.model.names[class_id]
                        
                        # Coordenadas da bounding box
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        
                        # Normalizar coordenadas (0-1)
                        height, width = frame.shape[:2]
                        normalized_box = {
                            "x1": float(x1 / width),
                            "y1": float(y1 / height),
                            "x2": float(x2 / width),
                            "y2": float(y2 / height)
                        }
                        
                        detection = {
                            "timestamp": timestamp,
                            "class_id": class_id,
                            "class_name": class_name,
                            "confidence": confidence,
                            "bounding_box": {
                                "pixel_coords": {
                                    "x1": int(x1),
                                    "y1": int(y1),
                                    "x2": int(x2),
                                    "y2": int(y2)
                                },
                                "normalized_coords": normalized_box
                            },
                            "center_point": {
                                "x": float((x1 + x2) / 2 / width),
                                "y": float((y1 + y2) / 2 / height)
                            },
                            "area": float((x2 - x1) * (y2 - y1) / (width * height))
                        }
                        
                        detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Erro ao detectar objetos no frame: {e}")
            return []