"""
Handler MQTT - Envia mensagens via MQTT quando alertas são detectados
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
from paho.mqtt.client import Client as MQTTClient

from ..event_system import AlertEvent, EventType

logger = logging.getLogger(__name__)

class MQTTHandler:
    """Handler para envio de mensagens MQTT"""
    
    def __init__(self, 
                 broker_host: str = "localhost",
                 broker_port: int = 1883,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 topic_prefix: str = "digefx/alerts"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client: Optional[MQTTClient] = None
        self.is_connected = False
        self._connection_retry_count = 0
        self._max_retries = 5
        
    async def initialize(self):
        """Inicializa a conexão MQTT"""
        try:
            self.client = mqtt.Client()
            
            # Configurar autenticação se fornecida
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Configurar callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            
            # Conectar
            await self._connect_with_retry()
            
            logger.info(f"MQTT Handler inicializado - Broker: {self.broker_host}:{self.broker_port}")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar MQTT Handler: {e}")
            raise
    
    async def cleanup(self):
        """Limpa recursos do handler"""
        if self.client and self.is_connected:
            self.client.disconnect()
            await asyncio.sleep(0.1)  # Dar tempo para desconectar
        logger.info("MQTT Handler finalizado")
    
    async def handle_event(self, event: AlertEvent) -> bool:
        """Processa evento de alerta enviando mensagem MQTT"""
        if not self.is_connected:
            logger.warning("MQTT não conectado, tentando reconectar...")
            if not await self._reconnect():
                return False
        
        try:
            # Preparar dados para MQTT
            mqtt_message = self._prepare_mqtt_message(event)
            
            # Definir tópicos
            topics = self._get_topics(event)
            
            # Enviar para cada tópico
            success = True
            for topic in topics:
                try:
                    result = self.client.publish(
                        topic=topic,
                        payload=json.dumps(mqtt_message, default=str),
                        qos=1,  # At least once delivery
                        retain=False
                    )
                    
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        logger.error(f"Erro ao publicar no tópico {topic}: {result.rc}")
                        success = False
                    else:
                        logger.debug(f"Mensagem MQTT enviada para {topic}")
                        
                except Exception as e:
                    logger.error(f"Erro ao enviar para tópico {topic}: {e}")
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Erro ao processar alerta MQTT: {e}")
            return False
    
    def _prepare_mqtt_message(self, event: AlertEvent) -> Dict[str, Any]:
        """Prepara mensagem MQTT a partir do evento de alerta"""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.detected_at.isoformat(),
            "camera": {
                "id": event.camera_id,
                "name": event.camera_name,
                "ip": event.camera_ip
            },
            "alert": {
                "type_id": event.alert_type_id,
                "type_code": event.alert_type_code,
                "type_name": event.alert_type_name,
                "severity": event.severity,
                "confidence": event.confidence
            },
            "detection": {
                "triggered_at": event.detected_at.isoformat(),
                "image_path": event.image_path,
                "video_clip_path": event.video_clip_path,
                "metadata": event.metadata
            },
            "source": "digefx-monitor",
            "version": "1.0"
        }
    
    def _get_topics(self, event: AlertEvent) -> list[str]:
        """Gera lista de tópicos MQTT para o evento"""
        topics = []
        
        # Tópico geral de alertas
        topics.append(f"{self.topic_prefix}/all")
        
        # Tópico por câmera
        topics.append(f"{self.topic_prefix}/camera/{event.camera_id}")
        
        # Tópico por tipo de alerta
        topics.append(f"{self.topic_prefix}/type/{event.alert_type_code}")
        
        # Tópico por severidade
        topics.append(f"{self.topic_prefix}/severity/{event.severity}")
        
        return topics
    
    async def _connect_with_retry(self):
        """Conecta ao broker MQTT com retry"""
        for attempt in range(self._max_retries):
            try:
                # Executar conexão em thread separada
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, 
                    self.client.connect, 
                    self.broker_host, 
                    self.broker_port, 
                    60  # keepalive
                )
                
                # Iniciar loop de rede
                self.client.loop_start()
                
                # Aguardar conexão
                for _ in range(50):  # 5 segundos
                    if self.is_connected:
                        break
                    await asyncio.sleep(0.1)
                
                if self.is_connected:
                    self._connection_retry_count = 0
                    return True
                else:
                    raise Exception("Timeout na conexão")
                    
            except Exception as e:
                self._connection_retry_count += 1
                logger.warning(f"Tentativa {attempt + 1} de conexão MQTT falhou: {e}")
                
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
        
        logger.error(f"Falha ao conectar MQTT após {self._max_retries} tentativas")
        return False
    
    async def _reconnect(self) -> bool:
        """Tenta reconectar ao MQTT"""
        if self._connection_retry_count >= self._max_retries:
            logger.error("Máximo de tentativas de reconexão MQTT atingido")
            return False
        
        return await self._connect_with_retry()
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback de conexão MQTT"""
        if rc == 0:
            self.is_connected = True
            logger.info("MQTT conectado com sucesso")
        else:
            self.is_connected = False
            logger.error(f"Falha na conexão MQTT: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback de desconexão MQTT"""
        self.is_connected = False
        if rc != 0:
            logger.warning(f"MQTT desconectado inesperadamente: {rc}")
        else:
            logger.info("MQTT desconectado")
    
    def _on_publish(self, client, userdata, mid):
        """Callback de publicação MQTT"""
        logger.debug(f"Mensagem MQTT publicada: {mid}")

def create_mqtt_handler(**kwargs) -> MQTTHandler:
    """Factory function para criar handler MQTT"""
    return MQTTHandler(**kwargs) 