"""
Controller de dispositivos e status do sistema
"""
import serial
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from services.auth_service import get_current_user, get_db
from services.network_service import get_public_ip
from models import DeviceStatus, HostStatus, DeviceLocation, User
from schemas import StatusResponse, DeviceStatusResponse, HostStatusResponse, LocationListResponse, DeviceLocationResponse
from config.settings import SERIAL_PORT, BAUD_RATE
import socket
import psutil

router = APIRouter()

# Serial communication lock
serial_lock = threading.Lock()


class SerialConfig(BaseModel):
    device_id: str | None = None
    relay1_time: float | None = None
    relay2_time: float | None = None
    min_voltage: float | None = None


def initialize_serial():
    """Inicializa a porta serial"""
    try:
        return serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"Error initializing serial: {e}")
        return None


# Initialize serial connection
ser = initialize_serial()


@router.post("/configure")
def configure(config: SerialConfig, current_user: User = Depends(get_current_user)):
    """Rota de configuração serial (protegida)"""
    config_dict = config.model_dump(exclude_unset=True, exclude_none=True)
    with serial_lock:  # Lock for safe write
        for key, value in config_dict.items():
            ser.write(f"{key.upper()}:{value}\n".encode())
            response = ser.readline().decode().strip()
            if response != "ACK":
                raise HTTPException(status_code=500, detail=f"Failed to set {key}")
    return {"status": "Configuration sent", **config_dict}


@router.get("/status", response_model=StatusResponse)
def get_device_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rota protegida para buscar status atual do dispositivo"""
    device_status = db.query(DeviceStatus).order_by(DeviceStatus.timestamp.desc()).first()
    host_status = db.query(HostStatus).order_by(HostStatus.timestamp.desc()).first()
    if not device_status and not host_status:
        raise HTTPException(status_code=404, detail="No status available")

    return {
        "device_status": DeviceStatusResponse(
            device_id=device_status.device_id,
            ignition=device_status.ignition,
            battery_voltage=device_status.battery_voltage,
            min_voltage=device_status.min_voltage,
            relay1_status=device_status.relay1_status,
            relay2_status=device_status.relay2_status,
            relay1_time=device_status.relay1_time,
            relay2_time=device_status.relay2_time,
            gps_status=device_status.gps_status,
            timestamp=device_status.timestamp.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) if device_status else None,
        "host_status": HostStatusResponse(
            host_ip=host_status.host_ip,
            public_ip=host_status.public_ip,
            cpu_usage=host_status.cpu_usage,
            ram_usage=host_status.ram_usage,
            disk_usage=host_status.disk_usage,
            temperature=host_status.temperature,
            online=host_status.online,
            timestamp=host_status.timestamp.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) if host_status else None
    }


@router.get("/locations/today", response_model=LocationListResponse)
def get_today_locations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rota protegida para buscar localizações do dispositivo do dia atual"""
    # Get today's date range (start and end of day)
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    # Query locations for today
    locations = db.query(DeviceLocation).filter(
        DeviceLocation.timestamp >= start_of_day,
        DeviceLocation.timestamp <= end_of_day
    ).order_by(DeviceLocation.timestamp.desc()).all()
    
    if not locations:
        return LocationListResponse(locations=[], total_count=0)
    
    location_responses = [
        DeviceLocationResponse(
            device_id=location.device_id,
            latitude=location.latitude,
            longitude=location.longitude,
            speed=location.speed,
            hdop=location.hdop,
            sats=location.sats,
            timestamp=location.timestamp.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) for location in locations
    ]
    
    return LocationListResponse(
        locations=location_responses,
        total_count=len(location_responses)
    ) 