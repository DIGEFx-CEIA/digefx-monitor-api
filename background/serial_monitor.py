"""
Monitor de comunicação serial em background
Refatorado para usar SerialManager centralizado
"""
import logging
from datetime import datetime

from models import DeviceStatus, DeviceLocation, SessionLocal
from .serial_manager import get_serial_manager, MessageType

logger = logging.getLogger(__name__)

# === Funções de compatibilidade para código legado ===

def send_serial_command(command: str) -> bool:
    """
    Envia comando via serial (compatibilidade com código antigo)
    
    DEPRECATED: Use serial_manager.send_command_sync() diretamente
    """
    manager = get_serial_manager()
    
    if not manager.is_running():
        logger.error("SerialManager não está em execução")
        return False
        
    # Enviar comando e aguardar ACK
    return manager.send_command_sync(command, wait_for_ack=True, timeout=2.0)


def process_serial_data(data: str):
    """
    Processa e armazena os dados de status recebidos do ESP32
    Formato: DEVICE_ID:xxx;IGNITION:On;BATTERY:12.5;...
    """
    try:
        logger.debug(f"Processando dados: {data}")
        
        # Parse dos dados
        parts = data.split(";")
        data_dict = {}
        
        for item in parts:
            if ":" in item:
                key, value = item.split(":", 1)
                data_dict[key] = value

        # Criar registro de status
        device_status = DeviceStatus(
            device_id=data_dict.get("DEVICE_ID", "unknown"),
            ignition=data_dict.get("IGNITION", "Off"),
            battery_voltage=float(data_dict.get("BATTERY", 0)),
            min_voltage=float(data_dict.get("MIN_VOLTAGE", 0)),
            relay1_status=data_dict.get("RELAY1", "Off"),
            relay1_time=float(data_dict.get("RELAY1_TIME", 0)),
            relay2_status=data_dict.get("RELAY2", "Off"),
            relay2_time=float(data_dict.get("RELAY2_TIME", 0)),
            gps_status=data_dict.get("GPS_STATUS", "Invalid"),
            timestamp=datetime.utcnow(),
        )

        # Criar registro de localização (se disponível)
        device_location = None
        if "LAT" in data_dict and "LNG" in data_dict:
            device_location = DeviceLocation(
                device_id=data_dict.get("DEVICE_ID", "unknown"),
                latitude=float(data_dict.get("LAT", 0)),
                longitude=float(data_dict.get("LNG", 0)),
                speed=float(data_dict.get("SPEED", 0)),
                hdop=float(data_dict.get("HDOP", 0)),
                sats=int(data_dict.get("SATS", 0)),
                timestamp=datetime.utcnow(),
            )

        # Salvar no banco de dados
        db = SessionLocal()
        try:
            db.add(device_status)
            
            # Salvar localização apenas se for válida
            if device_location and device_location.latitude != 0 and device_location.longitude != 0:
                db.add(device_location)
                
            db.commit()
            logger.info(f"✅ Status do dispositivo {device_status.device_id} salvo")
            
            # Enviar ACK para o ESP32
            manager = get_serial_manager()
            manager.send_command("ACK")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Erro ao processar dados seriais: {e}")


def handle_esp32_ready(data: str):
    """Callback para quando ESP32 está pronto"""
    logger.info("✅ ESP32 está pronto e inicializado")


def handle_heartbeat_timeout(data: str):
    """Callback para timeout de heartbeat"""
    logger.warning("⚠️ ESP32 reportou HEARTBEAT_TIMEOUT - aplicação pode ter falhado")


def handle_debug_message(data: str):
    """Callback para mensagens de debug do ESP32"""
    logger.debug(f"[ESP32] {data}")


def handle_unknown_message(data: str):
    """Callback para mensagens não reconhecidas"""
    logger.warning(f"⚠️ Mensagem não reconhecida: {data}")


def start_serial_monitoring():
    """
    Inicia o monitoramento serial usando SerialManager
    Registra callbacks para processar diferentes tipos de mensagens
    """
    logger.info("🚀 Iniciando monitoramento serial com SerialManager")
    
    # Obter instância do SerialManager
    manager = get_serial_manager()
    
    # Registrar callbacks para cada tipo de mensagem
    manager.register_callback(MessageType.STATUS_DATA, process_serial_data)
    manager.register_callback(MessageType.ESP32_READY, handle_esp32_ready)
    manager.register_callback(MessageType.HEARTBEAT_TIMEOUT, handle_heartbeat_timeout)
    manager.register_callback(MessageType.DEBUG, handle_debug_message)
    manager.register_callback(MessageType.UNKNOWN, handle_unknown_message)
    
    # Iniciar o SerialManager se ainda não estiver rodando
    if not manager.is_running():
        manager.start()
        
    logger.info("✅ Monitoramento serial iniciado") 