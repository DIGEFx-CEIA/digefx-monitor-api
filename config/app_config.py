"""
Configurações da aplicação
"""
import os
from pathlib import Path
from typing import Optional

class AppConfig:
    """Configurações da aplicação"""
    
    # Configurações gerais
    APP_NAME: str = "DIGEF-X Power Management API"
    APP_VERSION: str = "2.0.0"
    APP_DESCRIPTION: str = "API para monitoramento de energia e gerenciamento de dispositivos"

    # Diretórios
    BASE_DIR = Path(__file__).parent.absolute()
    VIDEO_DIR = Path("/home/digefx/Documents/digefx_monitor/frigate/storage/recordings/2025-08-06")  # No Docker será mapeado via volume
    METADATA_DIR = BASE_DIR / "metadata"
    LOGS_DIR = BASE_DIR / "logs"
    
    # Configurações de detecção
    MEDIAPIPE_CONFIDENCE = float(os.getenv("MEDIAPIPE_CONFIDENCE", 0.5))
    YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", 0.6))
    YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
    
    
    # Configurações de servidor
    HOST: str = "0.0.0.0"
    PORT: int = 7000
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Configurações de banco de dados
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    
    # Configurações de segurança
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Configurações de serial
    SERIAL_PORT: str = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    SERIAL_BAUDRATE: int = int(os.getenv("SERIAL_BAUDRATE", "9600"))
    SERIAL_TIMEOUT: int = int(os.getenv("SERIAL_TIMEOUT", "1"))
    
    # Configurações de monitoramento
    CAMERA_MONITOR_INTERVAL: int = int(os.getenv("CAMERA_MONITOR_INTERVAL", "10"))
    HOST_MONITOR_INTERVAL: int = int(os.getenv("HOST_MONITOR_INTERVAL", "30"))
    
    # Configurações de rede
    NETWORK_TIMEOUT: int = int(os.getenv("NETWORK_TIMEOUT", "5"))
    
    # Configurações de alertas
    ALERT_RETENTION_DAYS: int = int(os.getenv("ALERT_RETENTION_DAYS", "30"))
    
    # Configurações de CORS
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    @classmethod
    def get_database_url(cls) -> str:
        """Retorna URL do banco de dados"""
        return cls.DATABASE_URL
    
    @classmethod
    def get_secret_key(cls) -> str:
        """Retorna chave secreta"""
        return cls.SECRET_KEY
    
    @classmethod
    def is_debug(cls) -> bool:
        """Verifica se está em modo debug"""
        return cls.DEBUG

    @classmethod
    def ensure_directories(cls):
        """Garante que os diretórios necessários existem"""
        cls.METADATA_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)
        cls.VIDEO_DIR.mkdir(exist_ok=True)


# Instância global da configuração
app_config = AppConfig() 