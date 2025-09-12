"""
Monitor de comunicação serial em background
"""
import serial
import threading
import time
from datetime import datetime

from config import app_config
from models import DeviceStatus, DeviceLocation, SessionLocal

# Serial communication lock
serial_lock = threading.Lock()


def initialize_serial():
    """Inicializa a porta serial"""
    try:
        return serial.Serial(app_config.SERIAL_PORT, app_config.BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"Error initializing serial: {e}")
        return None


def process_serial_data(data):
    """Processa e armazena os dados recebidos"""
    print(f"Received: {data}")
    parts = data.split(";")
    data_dict = {item.split(":")[0]: item.split(":")[1] for item in parts if ":" in item}

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

    device_location = DeviceLocation(
        device_id=data_dict.get("DEVICE_ID", "unknown"),
        latitude=float(data_dict.get("LAT", 0)),
        longitude=float(data_dict.get("LNG", 0)),
        speed=float(data_dict.get("SPEED", 0)),
        hdop=float(data_dict.get("HDOP", 0)),
        sats=int(data_dict.get("SATS", 0)),
        timestamp=datetime.utcnow(),
    )

    db = SessionLocal()
    try:
        db.add(device_status)
        # Just save the location if it's valid
        if device_location.latitude != 0 and device_location.longitude != 0:
            db.add(device_location)
        db.commit()
    finally:
        db.close()

    # Send acknowledgment back to ESP32
    return "ACK"


def read_serial_data():
    """Lê dados seriais em background"""
    ser = initialize_serial()
    
    while True:
        try:
            with serial_lock:  # Lock for safe read
                if ser and ser.in_waiting:
                    line = ser.readline().decode().strip()
                    if line and line != "ACK" and line.startswith("DEVICE_ID"):
                        ack = process_serial_data(line)
                        if ser:
                            ser.write(f'{ack}\n'.encode())
        except serial.SerialException as e:
            print(f"Serial Exception: {e}")
            time.sleep(5)  # Wait before retrying
            ser = initialize_serial()  # Reinitialize the serial connection
        except Exception as e:
            print(f"Error in serial monitoring: {e}")
            time.sleep(1)


def start_serial_monitoring():
    """Inicia o monitoramento serial em thread separada"""
    threading.Thread(target=read_serial_data, daemon=True).start()
    print("Serial monitoring started") 