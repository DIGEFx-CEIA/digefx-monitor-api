"""
Event Handlers para o sistema de alertas

4 Handlers essenciais:
- DatabaseHandler: Salva alertas no banco de dados
- MQTTHandler: Publica alertas via MQTT
- AMQPHandler: Envia alertas para RabbitMQ/AMQP
- FrigateHandler: Registra alertas no Frigate
"""

from .mqtt_handler import MQTTHandler
from .amqp_handler import AMQPHandler
from .database_handler import DatabaseHandler
from .frigate_handler import FrigateHandler

__all__ = [
    "MQTTHandler",
    "AMQPHandler", 
    "DatabaseHandler",
    "FrigateHandler"
] 