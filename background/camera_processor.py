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
import cv2
import mediapipe as mp
import numpy as np
from ultralytics import YOLO
import collections

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
    
    DETECTION_WINDOW_SECONDS = 3
    DETECTION_THRESHOLD = 10
    ALERT_COOLDOWN_SECONDS = 5

    def __init__(self, camera_config: CameraConfig, model_path: str = "last.pt"):
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
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.yolo_model = None  # Modelo YOLO será carregado sob demanda
        self.model_path = model_path  # Caminho do modelo customizado ("last.pt" por padrão)
        self._alert_trackers = collections.defaultdict(lambda: {"last_alert_time": 0, "timestamps": []})
        
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
        Loop principal de processamento usando MediaPipe para detectar presença de pessoa.
        Quando uma pessoa é detectada por 30 segundos contínuos, aciona o gatilho (por enquanto, apenas loga).
        """
        frame_interval = 1.0 / 30.0  # 30 FPS
        pessoa_presente = False
        tempo_inicio_presenca = None
        TEMPO_GATILHO = 30  # segundos
        while not self._stop_event.is_set() and self.config.is_active:
            try:
                start_time = time.time()
                frame_data = await self._capture_frame()
                logger.warning(f"MediaPipe. Frame capturado da câmera {self.config.camera_id}")
                if not frame_data or frame_data.get("frame") is None:
                    logger.warning(f"Frame vazio ou inválido da câmera {self.config.camera_id}, aguardando próximo frame.")
                    await asyncio.sleep(frame_interval)
                    continue
                pessoa_detectada = self.detect_person_mediapipe(frame_data.get("frame"))

                if pessoa_detectada:
                    if not pessoa_presente:
                        tempo_inicio_presenca = datetime.utcnow()
                        pessoa_presente = True
                    else:
                        tempo_atual = datetime.utcnow()
                        tempo_presenca = (tempo_atual - tempo_inicio_presenca).total_seconds()
                        if tempo_presenca >= TEMPO_GATILHO:
                            logger.info(f"Pessoa detectada por {TEMPO_GATILHO} segundos. Gatilho acionado!")
                            await self._yolo_inference_loop()
                            # Após o loop YOLO, resetar contadores
                            pessoa_presente = False
                            tempo_inicio_presenca = None
                else:
                    pessoa_presente = False
                    tempo_inicio_presenca = None

                # Atualizar estatísticas
                self.processing_stats["frames_processed"] += 1
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
        rtsp_url = "rtsp://admin:digefx@2024@" + self.config.camera_ip + ":" + str(self.config.camera_port) + "/cam/realmonitor?channel=1&subtype=0"
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            logger.error(f"Erro ao conectar na câmera: {rtsp_url}")
            await asyncio.sleep(2)  # Usar sleep assíncrono
            return None
        ret, frame = cap.read()
        cap.release()
        
        # return the object with dimensions and data using OpenCV
        if frame is None:
            logger.warning(f"Frame capturado da câmera {self.config.camera_id} está vazio")
            return None
        if not ret:
            logger.warning(f"Falha ao capturar frame da câmera {self.config.camera_id}")
            return None
        self.processing_stats["frames_processed"] += 1
        return {
            "timestamp": datetime.utcnow(),
            "frame_id": self.processing_stats["frames_processed"],
            "frame": frame,
            "ret": ret,
        }
    
    async def _process_frame(self, frame_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Processa frame com IA para detectar objetos/eventos (YOLO).
        Executa modelo de IA no frame e retorna lista de detecções relevantes.
        """
        # Executar inferência YOLO
        detections = self.infer_yolo(frame_data.get("frame"))
        results = []
        for det in detections:
            alert_type = self.config.alert_types.get(det["class_name"], {})
            if not alert_type:
                continue  # Ignorar classes não configuradas
            detection = {
                "alert_code": det["class_name"],
                "alert_type": alert_type,
                "confidence": det["confidence"],
                "bbox": det["bbox"],
                "frame_data": frame_data,
                "detected_at": datetime.utcnow()
            }
            results.append(detection)
        return results
    
    def should_trigger_alert(self, alert_code: str) -> bool:
        """Verifica se um alerta deve ser disparado para a classe, respeitando janela e cooldown."""
        tracker = self._alert_trackers[alert_code]
        current_time = time.time()
        tracker["timestamps"].append(current_time)
        # Manter apenas timestamps dentro da janela
        tracker["timestamps"] = [ts for ts in tracker["timestamps"] if current_time - ts <= self.DETECTION_WINDOW_SECONDS]
        current_count = len(tracker["timestamps"])
        if current_count >= self.DETECTION_THRESHOLD:
            if (current_time - tracker["last_alert_time"]) > self.ALERT_COOLDOWN_SECONDS:
                tracker["last_alert_time"] = current_time
                return True
        return False

    async def _handle_detection(self, detection: Dict[str, Any]):
        """Processa uma detecção e gera evento de alerta, respeitando janela/cooldown."""
        alert_type = detection["alert_type"]
        alert_code = detection["alert_code"]
        if not alert_type:
            logger.warning(f"Tipo de alerta não encontrado para código {alert_code}")
            return
        if not self.should_trigger_alert(alert_code):
            logger.debug(f"Alerta {alert_code} não disparado (janela/cooldown)")
            return
        # Criar evento de alerta
        event = create_alert_event(
            camera_id=self.config.camera_id,
            camera_name=self.config.camera_name,
            camera_ip=self.config.camera_ip,
            alert_type_code=alert_code,
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
        logger.info(f"Alerta detectado: {alert_code} na câmera {self.config.camera_name} (confiança: {detection['confidence']:.2f})")
    
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

    def detect_person_mediapipe(self, frame: np.ndarray) -> bool:
        """Detecta presença de pessoa usando MediaPipe Pose"""
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_frame)
        return results.pose_landmarks is not None

    def load_yolo_model(self, model_path: str = None):
        """Carrega o modelo YOLO, priorizando o customizado se fornecido."""
        path_to_load = model_path or self.model_path or "yolov8n.pt"
        if self.yolo_model is None or getattr(self.yolo_model, 'model_path', None) != path_to_load:
            try:
                self.yolo_model = YOLO(path_to_load)
                self.yolo_model.model_path = path_to_load  # Marcar caminho carregado
                logger.info(f"Modelo YOLO carregado de {path_to_load}")
            except Exception as e:
                logger.error(f"Erro ao carregar modelo YOLO: {e}")
                self.yolo_model = None
        return self.yolo_model

    def infer_yolo(self, frame: np.ndarray, conf_threshold: float = 0.5) -> list:
        """Executa inferência YOLO no frame e retorna detecções."""
        model = self.load_yolo_model()
        if model is None:
            logger.error("YOLO não carregado. Não é possível inferir.")
            return []
        try:
            results = model(frame, conf=conf_threshold, verbose=False)
            detections = []
            for r in results:
                for box in r.boxes:
                    class_id = int(box.cls[0])
                    class_name = model.names[class_id]
                    conf = float(box.conf[0])
                    bbox = box.xyxy[0].cpu().numpy().tolist()  # [x1, y1, x2, y2]
                    detections.append({
                        "class_id": class_id,
                        "class_name": class_name,
                        "confidence": conf,
                        "bbox": bbox
                    })
            return detections
        except Exception as e:
            logger.error(f"Erro na inferência YOLO: {e}")
            return []

    async def _yolo_inference_loop(self, frame_interval: float = 1.0/10.0):
        """
        Loop de inferência usando YOLO, executado enquanto a pessoa estiver presente.
        Aplica regras de negócio para disparo de alertas baseadas em combinações/ausências de classes.
        """
        logger.info("Iniciando loop de inferência YOLO...")
        monitored_classes = set(self.config.enabled_alerts)
        adversidades_diretas = {"fumando_cigarro", "sem_cinto", "usando_celular"}
        while not self._stop_event.is_set() and self.config.is_active:
            frame_data = await self._capture_frame()
            logger.warning(f"Yolo. Frame capturado da câmera {self.config.camera_id}")
            if not frame_data or frame_data.get("frame") is None:
                await asyncio.sleep(frame_interval)
                continue

            detections = await self._process_frame(frame_data)
            detected_classes = set()
            det_map = {}
            for det in detections:
                detected_classes.add(det["alert_code"])
                det_map[det["alert_code"]] = det

            # Regras de negócio:
            # 1. Se detectar "pessoa" e não detectar "com_capacete", dispara "pessoa_sem_capacete"
            if "pessoa" in detected_classes:
                if "com_capacete" in monitored_classes and "com_capacete" not in detected_classes:
                    # Criar detecção sintética para pessoa_sem_capacete
                    det = det_map["pessoa"]
                    fake_detection = det.copy()
                    fake_detection["alert_code"] = "pessoa_sem_capacete"
                    fake_detection["alert_type"] = self.config.alert_types.get("pessoa_sem_capacete", {})
                    await self._handle_detection(fake_detection)
                if "com_luva" in monitored_classes and "com_luva" not in detected_classes:
                    det = det_map["pessoa"]
                    fake_detection = det.copy()
                    fake_detection["alert_code"] = "pessoa_sem_luva"
                    fake_detection["alert_type"] = self.config.alert_types.get("pessoa_sem_luva", {})
                    await self._handle_detection(fake_detection)

            # 2. Adversidades diretas
            for adversity in adversidades_diretas:
                if adversity in detected_classes and adversity in monitored_classes:
                    await self._handle_detection(det_map[adversity])

            # 3. Outras detecções configuradas
            for det in detections:
                if det["alert_code"] in monitored_classes and det["alert_code"] not in adversidades_diretas:
                    await self._handle_detection(det)

            # Verificar se a pessoa ainda está presente usando MediaPipe
            frame = frame_data.get("frame")
            pessoa_ainda_presente = self.detect_person_mediapipe(frame) if frame is not None else False
            if not pessoa_ainda_presente:
                logger.info("Pessoa não detectada, encerrando loop YOLO.")
                break

            await asyncio.sleep(frame_interval)

class CameraProcessorFactory:
    """Factory para criar processadores de câmera"""
    
    @staticmethod
    def create_processor(camera_config: CameraConfig, model_path: str = "last.pt") -> CameraProcessor:
        """Cria um novo processador para a câmera, permitindo modelo customizado"""
        return CameraProcessor(camera_config, model_path) 