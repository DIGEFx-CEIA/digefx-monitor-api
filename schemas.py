from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class DeviceStatusResponse(BaseModel):
    device_id: str
    ignition: Optional[str]
    battery_voltage: Optional[float]
    min_voltage: Optional[float]
    relay1_status: Optional[str]
    relay2_status: Optional[str]
    relay1_time: Optional[float]
    relay2_time: Optional[float]
    gps_status: Optional[str]
    timestamp: str

class DeviceLocationResponse(BaseModel):
    device_id: str
    latitude: Optional[float]
    longitude: Optional[float]
    speed: Optional[float]
    hdop: Optional[float]
    sats: Optional[int]
    timestamp: str

class LocationListResponse(BaseModel):
    locations: List[DeviceLocationResponse]
    total_count: int

class HostStatusResponse(BaseModel):
    host_ip: Optional[str]
    public_ip: Optional[str]
    cpu_usage: Optional[float]
    ram_usage: Optional[float]
    disk_usage: Optional[float]
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