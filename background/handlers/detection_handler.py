import logging
import time
import asyncio
import threading
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
        
        # Pool de modelos reutilizáveis (thread-safe)
        self._model_pool = []
        self._model_lock = threading.Lock()
        self._models_in_use = set()
        
        try:
            logger.info(f"Carregando modelo YOLO principal: {app_config.YOLO_MODEL}")
            self.model = YOLO(app_config.YOLO_MODEL)
            logger.info("Modelo YOLO principal carregado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao carregar modelo YOLO: {e}")
            raise

    async def initialize(self):
        """Inicializa o handler de detecção com pré-carregamento de modelos"""
        if self.is_initialized:
            return
            
        logger.info("🚀 Inicializando Detection Handler com pré-carregamento...")
        
        # Pré-carregar e aquecer modelos para todas as threads
        await self._preload_thread_models()
        
        self.is_initialized = True
        logger.info("✅ Detection Handler inicializado com modelos pré-carregados")
    
    async def _preload_thread_models(self):
        """Pré-carrega e aquece modelos YOLO para todas as threads trabalhadoras"""
        try:
            logger.info(f"🔥 Pré-carregando {self.max_workers} modelos YOLO...")
            start_time = time.time()
            
            # Usar ThreadPoolExecutor para carregar modelos em paralelo
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Criar tasks para carregar um modelo por worker
                futures = [
                    loop.run_in_executor(executor, self._load_and_warm_model, i+1)
                    for i in range(self.max_workers)
                ]
                
                # Aguardar todos os modelos serem carregados
                thread_ids = await asyncio.gather(*futures)
                
            total_time = time.time() - start_time
            logger.info(f"✅ {len(thread_ids)} modelos pré-carregados e aquecidos em {total_time:.2f}s")
            logger.info(f"🎯 Thread IDs com modelos: {thread_ids}")
            
        except Exception as e:
            logger.error(f"❌ Erro no pré-carregamento: {e}")
            # Continuar mesmo com erro - modelos serão carregados sob demanda
    
    def _load_and_warm_model(self, worker_id: int) -> int:
        """Carrega e aquece um modelo YOLO para o pool de modelos"""
        try:
            logger.info(f"🔄 Worker {worker_id}: Carregando modelo para pool")
            
            load_start = time.time()
            
            # Carregar modelo
            model = YOLO(app_config.YOLO_MODEL)
            
            # Aquecer modelo com frame dummy
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            _ = model(dummy_frame, conf=0.5, verbose=False)
            
            # Adicionar ao pool thread-safe
            with self._model_lock:
                self._model_pool.append(model)
            
            load_time = time.time() - load_start
            logger.info(f"✅ Worker {worker_id}: Modelo carregado e aquecido em {load_time:.2f}s (pool: {len(self._model_pool)})")
            
            return worker_id
            
        except Exception as e:
            logger.error(f"❌ Worker {worker_id}: Erro ao carregar modelo - {e}")
            return -1
    
    def get_thread_model(self, batch_id: int = 0) -> YOLO:
        """Obtém modelo YOLO do pool pré-carregado (thread-safe)"""
        with self._model_lock:
            # Tentar obter modelo do pool
            if self._model_pool:
                model = self._model_pool.pop(0)  # Pegar primeiro modelo disponível
                logger.debug(f"⚡ [Lote {batch_id}] Usando modelo do pool (restam: {len(self._model_pool)})")
                return model
            else:
                # Fallback: usar modelo principal (pode causar contenção)
                logger.warning(f"🔄 [Lote {batch_id}] Pool vazio, usando modelo principal")
                return self.model
    
    def return_thread_model(self, model: YOLO, batch_id: int = 0):
        """Retorna modelo para o pool após uso"""
        if model != self.model:  # Não retornar modelo principal
            with self._model_lock:
                self._model_pool.append(model)
                logger.debug(f"♻️ [Lote {batch_id}] Modelo retornado ao pool (total: {len(self._model_pool)})")

    async def cleanup(self):
        """Limpa recursos do handler incluindo modelos pré-carregados"""
        try:
            logger.info("🧹 Limpando recursos do Detection Handler...")
            
            with self._model_lock:
                num_models = len(self._model_pool)
                self._model_pool.clear()
                self._models_in_use.clear()
                logger.info(f"✅ {num_models} modelos do pool removidos da memória")
            
            logger.info("🧹 Detection Handler finalizado")
        except Exception as e:
            logger.error(f"❌ Erro na limpeza: {e}")

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
                logger.warning(f"Nenhuma detecção do MediaPipe encontrada no evento. Metadata disponível: {list(event.metadata.keys())}")
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
            
            logger.info(f"📦 Dividindo em {len(batches)} lotes (batch_size={batch_size}, max_workers={self.max_workers})")
            for i, batch in enumerate(batches):
                logger.info(f"  Lote {i+1}: frames {batch[0]}-{batch[-1]} ({len(batch)} frames)")
            
            # Executar processamento paralelo
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                logger.info(f"🚀 Iniciando {len(batches)} workers paralelos...")
                
                futures = [
                    loop.run_in_executor(
                        executor, 
                        self.process_frame_batch, 
                        event.file_path, 
                        batch, 
                        fps,
                        event.camera.enabled_alerts,
                        i+1  # batch_id para logs
                    ) 
                    for i, batch in enumerate(batches)
                ]
                
                logger.info("⏳ Aguardando conclusão dos lotes...")
                # Aguardar todos os lotes terminarem com progress
                batch_results = []
                for i, future in enumerate(asyncio.as_completed(futures)):
                    result = await future
                    batch_results.append(result)
                    logger.info(f"✅ Lote {i+1}/{len(futures)} concluído: {result['frames_processed']} frames processados")
            
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
    
    def process_frame_batch(self, video_path: str, frame_indices: List[int], fps: float, enabled_alerts: List[str], batch_id: int = 0) -> Dict:
        """Processa um lote de frames de forma síncrona (executado em thread separada)"""
        try:
            logger.info(f"🔄 [Lote {batch_id}] Iniciando processamento de {len(frame_indices)} frames")
            
            # Obter modelo YOLO do pool pré-carregado
            thread_model = self.get_thread_model(batch_id)
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"❌ [Lote {batch_id}] Erro ao abrir vídeo: {video_path}")
                return {"frames_processed": 0, "alert_counts": {}}
            
            alert_counts = {}
            frames_processed = 0
            monitored_classes = set(enabled_alerts)
            
            logger.info(f"🎯 [Lote {batch_id}] Alertas monitorados: {monitored_classes}")
            
            # Log de progresso a cada 10% dos frames
            progress_interval = max(1, len(frame_indices) // 10)
            
            for i, frame_idx in enumerate(frame_indices):
                # Ir para o frame específico
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    logger.debug(f"⚠️ [Lote {batch_id}] Frame {frame_idx} não pôde ser lido")
                    continue
                
                # Log de progresso
                if i % progress_interval == 0 or i == len(frame_indices) - 1:
                    progress = (i + 1) / len(frame_indices) * 100
                    logger.info(f"📊 [Lote {batch_id}] Progresso: {progress:.1f}% ({i+1}/{len(frame_indices)} frames)")
                
                timestamp = frame_idx / fps
                
                # Executar YOLO no frame usando modelo da thread
                detections = self.detect_objects_in_frame(frame, timestamp, thread_model)
                
                logger.debug(f"🔍 [Lote {batch_id}] Frame {frame_idx}: {len(detections)} detecções")
                
                # Processar detecções seguindo a lógica do camera_processor
                detected_classes = set()
                for detection in detections:
                    class_name = detection.get("class_name", "")
                    # Adicionar todas as classes detectadas pelo YOLO (não filtrar por monitored_classes)
                    detected_classes.add(class_name)
                
                # Aplicar regras de negócio similar ao _yolo_inference_loop
                # Modelo retorna classes em MAIÚSCULAS: PESSOA, COM_CAPACETE, COM_LUVA, etc.
                # Banco tem códigos em inglês: NO_HELMET, SMOKING, etc.
                
                if "PESSOA" in detected_classes:
                    logger.debug(f"👤 [Lote {batch_id}] Frame {frame_idx}: PESSOA detectada, classes: {detected_classes}")
                    
                    # Se detectou pessoa mas não detectou capacete → NO_HELMET (apenas se habilitado)
                    if "COM_CAPACETE" not in detected_classes and "NO_HELMET" in monitored_classes:
                        alert_counts["NO_HELMET"] = alert_counts.get("NO_HELMET", 0) + 1
                        logger.debug(f"🪖 [Lote {batch_id}] Frame {frame_idx}: NO_HELMET detectado (sem capacete)")
                    elif "COM_CAPACETE" in detected_classes:
                        logger.debug(f"✅ [Lote {batch_id}] Frame {frame_idx}: COM_CAPACETE detectado")
                    
                    # Se detectou pessoa mas não detectou luva → NO_GLOVES (apenas se habilitado)
                    if "COM_LUVA" not in detected_classes and "NO_GLOVES" in monitored_classes:
                        alert_counts["NO_GLOVES"] = alert_counts.get("NO_GLOVES", 0) + 1
                        logger.debug(f"🧤 [Lote {batch_id}] Frame {frame_idx}: NO_GLOVES detectado (sem luva)")
                    elif "COM_LUVA" in detected_classes:
                        logger.debug(f"✅ [Lote {batch_id}] Frame {frame_idx}: COM_LUVA detectado")
                
                # Adversidades diretas - mapear classes do modelo para códigos do banco
                class_to_alert_mapping = {
                    "FUMANDO_CIGARRO": "SMOKING",
                    "SEM_CINTO": "NO_SEAT_BELT", 
                    "USANDO_CELULAR": "USING_CELL_PHONE"
                }
                
                for model_class, alert_code in class_to_alert_mapping.items():
                    if model_class in detected_classes and alert_code in monitored_classes:
                        alert_counts[alert_code] = alert_counts.get(alert_code, 0) + 1
                
                frames_processed += 1
            
            cap.release()
            
            # Retornar modelo ao pool
            self.return_thread_model(thread_model, batch_id)
            
            logger.info(f"✅ [Lote {batch_id}] Concluído: {frames_processed} frames, alertas: {alert_counts}")
            return {"frames_processed": frames_processed, "alert_counts": alert_counts}
            
        except Exception as e:
            logger.error(f"Erro ao processar lote de frames: {e}")
            # Tentar retornar modelo mesmo em caso de erro
            try:
                self.return_thread_model(thread_model, batch_id)
            except:
                pass
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
        
    def detect_objects_in_frame(self, frame, timestamp: float, model: YOLO = None) -> List[Dict]:
        """Detecta objetos em um frame usando YOLO"""
        try:
            # Usar modelo fornecido ou modelo principal
            yolo_model = model if model is not None else self.model
            
            # Fazer detecção
            results = yolo_model(frame, conf=app_config.YOLO_CONFIDENCE, verbose=False)
            
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # Obter informações da detecção
                        class_id = int(box.cls.cpu().numpy())
                        confidence = float(box.conf.cpu().numpy())
                        class_name = yolo_model.names[class_id]
                        
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