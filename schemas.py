from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DeviceStatusResponse(BaseModel):
    device_id: str
    ignition: str
    battery_voltage: float
    min_voltage: float
    relay1_status: str
    relay2_status: str
    relay1_time: float
    relay2_time: float
    timestamp: datetime

class HostStatusResponse(BaseModel):
    host_ip: str
    public_ip: str
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    temperature: Optional[float] = None
    online:bool
    timestamp: datetime

class CameraStatusResponse(BaseModel):
    camera1_ip: Optional[str]
    camera1_connected: bool
    camera2_ip: Optional[str]
    camera2_connected: bool
    camera3_ip: Optional[str]
    camera3_connected: bool
    camera4_ip: Optional[str]
    camera4_connected: bool
    timestamp: datetime

class StatusResponse(BaseModel):
    device_status: Optional[DeviceStatusResponse]
    host_status: Optional[HostStatusResponse]
    camera_status: Optional[CameraStatusResponse]