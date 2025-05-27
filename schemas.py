from datetime import datetime
from typing import Optional, List
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
    gps_status: str
    timestamp: str

class DeviceLocationResponse(BaseModel):
    device_id: str
    latitude: float
    longitude: float
    speed: float
    hdop: float
    sats: int
    timestamp: str

class LocationListResponse(BaseModel):
    locations: List[DeviceLocationResponse]
    total_count: int

class HostStatusResponse(BaseModel):
    host_ip: str
    public_ip: str
    cpu_usage: float
    ram_usage: float
    disk_usage: float
    temperature: Optional[float] = None
    online:bool
    timestamp: str

class CameraStatusResponse(BaseModel):
    camera1_ip: Optional[str]
    camera1_connected: bool
    camera2_ip: Optional[str]
    camera2_connected: bool
    camera3_ip: Optional[str]
    camera3_connected: bool
    camera4_ip: Optional[str]
    camera4_connected: bool
    timestamp: str

class StatusResponse(BaseModel):
    device_status: Optional[DeviceStatusResponse]
    host_status: Optional[HostStatusResponse]
    camera_status: Optional[CameraStatusResponse]