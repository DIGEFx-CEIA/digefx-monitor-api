"""
Configurações gerais da aplicação
"""
import os
from dotenv import load_dotenv

load_dotenv()

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "device/status"

# Serial communication configuration
SERIAL_PORT = "/dev/ttyUSB0"  # Update this according to your system
BAUD_RATE = 115200

# JWT configuration
SECRET_KEY = "digefxsecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 