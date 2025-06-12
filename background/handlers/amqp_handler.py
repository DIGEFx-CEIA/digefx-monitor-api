"""
Handler AMQP - Envia mensagens via AMQP/RabbitMQ quando alertas são detectados
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import aio_pika
from aio_pika import Message, ExchangeType
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractExchange

from ..event_system import AlertEvent, EventType

logger = logging.getLogger(__name__)

class AMQPHandler:
    """Handler para envio de mensagens AMQP"""
    
    def __init__(self,
                 amqp_url: str = "amqp://guest:guest@localhost:5672/",
                 exchange_name: str = "digefx.alerts",
                 exchange_type: str = "topic",
                 routing_key_prefix: str = "alert"):
        self.amqp_url = amqp_url
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.routing_key_prefix = routing_key_prefix
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.exchange: Optional[AbstractExchange] = None
        self.is_connected = False
        self._connection_retry_count = 0
        self._max_retries = 5
        
    async def initialize(self):
        """Inicializa a conexão AMQP"""
        try:
            # Conectar com retry
            await self._connect_with_retry()
            
            logger.info(f"AMQP Handler inicializado - URL: {self.amqp_url}")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar AMQP Handler: {e}")
            raise
    
    async def cleanup(self):
        """Limpa recursos do handler"""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            logger.info("AMQP Handler finalizado")
        except Exception as e:
            logger.error(f"Erro ao finalizar AMQP Handler: {e}")
    
    async def handle_event(self, event: AlertEvent) -> bool:
        """Processa evento de alerta enviando mensagem AMQP"""
        if not self.is_connected:
            logger.warning("AMQP não conectado, tentando reconectar...")
            if not await self._reconnect():
                return False
        
        try:
            # Preparar dados para AMQP
            amqp_message = self._prepare_amqp_message(event)
            
            # Definir routing keys
            routing_keys = self._get_routing_keys(event)
            
            # Enviar para cada routing key
            success = True
            for routing_key in routing_keys:
                try:
                    # Criar mensagem
                    message = Message(
                        body=json.dumps(amqp_message, default=str).encode(),
                        headers={
                            "event_type": event.event_type.value,
                            "camera_id": event.camera_id,
                            "alert_type": event.alert_type_code,
                            "severity": event.severity,
                            "timestamp": event.detected_at.isoformat()
                        },
                        content_type="application/json",
                        delivery_mode=2  # Persistent message
                    )
                    
                    # Publicar mensagem
                    await self.exchange.publish(
                        message=message,
                        routing_key=routing_key
                    )
                    
                    logger.debug(f"Mensagem AMQP enviada com routing key: {routing_key}")
                    
                except Exception as e:
                    logger.error(f"Erro ao enviar AMQP com routing key {routing_key}: {e}")
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Erro ao processar alerta AMQP: {e}")
            return False
    
    def _prepare_amqp_message(self, event: AlertEvent) -> Dict[str, Any]:
        """Prepara mensagem AMQP a partir do evento de alerta"""
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
    
    def _get_routing_keys(self, event: AlertEvent) -> list[str]:
        """Gera lista de routing keys AMQP para o evento"""
        routing_keys = []
        
        # Routing key geral
        routing_keys.append(f"{self.routing_key_prefix}.all")
        
        # Routing key por câmera
        routing_keys.append(f"{self.routing_key_prefix}.camera.{event.camera_id}")
        
        # Routing key por tipo de alerta
        routing_keys.append(f"{self.routing_key_prefix}.type.{event.alert_type_code}")
        
        # Routing key por severidade
        routing_keys.append(f"{self.routing_key_prefix}.severity.{event.severity}")
        
        # Routing key combinada
        routing_keys.append(f"{self.routing_key_prefix}.camera.{event.camera_id}.type.{event.alert_type_code}")
        
        return routing_keys
    
    async def _connect_with_retry(self):
        """Conecta ao AMQP com retry"""
        for attempt in range(self._max_retries):
            try:
                # Conectar
                self.connection = await aio_pika.connect_robust(
                    self.amqp_url,
                    heartbeat=600,  # 10 minutes
                    blocked_connection_timeout=300,  # 5 minutes
                )
                
                # Criar canal
                self.channel = await self.connection.channel()
                await self.channel.set_qos(prefetch_count=10)
                
                # Declarar exchange
                self.exchange = await self.channel.declare_exchange(
                    name=self.exchange_name,
                    type=ExchangeType.TOPIC,
                    durable=True
                )
                
                self.is_connected = True
                self._connection_retry_count = 0
                
                logger.info(f"AMQP conectado - Exchange: {self.exchange_name}")
                return True
                
            except Exception as e:
                self._connection_retry_count += 1
                logger.warning(f"Tentativa {attempt + 1} de conexão AMQP falhou: {e}")
                
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Backoff exponencial
        
        logger.error(f"Falha ao conectar AMQP após {self._max_retries} tentativas")
        self.is_connected = False
        return False
    
    async def _reconnect(self) -> bool:
        """Tenta reconectar ao AMQP"""
        if self._connection_retry_count >= self._max_retries:
            logger.error("Máximo de tentativas de reconexão AMQP atingido")
            return False
        
        # Limpar conexões existentes
        if self.connection:
            try:
                await self.connection.close()
            except:
                pass
        
        self.connection = None
        self.channel = None
        self.exchange = None
        self.is_connected = False
        
        return await self._connect_with_retry()

def create_amqp_handler(**kwargs) -> AMQPHandler:
    """Factory function para criar handler AMQP"""
    return AMQPHandler(**kwargs) 