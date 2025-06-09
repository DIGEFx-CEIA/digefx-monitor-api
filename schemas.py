from datetime import datetime
from typing import Optional, List, Dict, Any
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

class StatusResponse(BaseModel):
    device_status: Optional[DeviceStatusResponse]
    host_status: Optional[HostStatusResponse]

# Alert Type schemas
class AlertTypeCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical

class AlertTypeResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str

class AlertTypeListResponse(BaseModel):
    alert_types: List[AlertTypeResponse]
    total_count: int

# Camera schemas
class CameraCreate(BaseModel):
    name: str
    ip_address: str
    port: int = 80
    enabled_alerts: List[str] = []  # List of alert type codes

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    enabled_alerts: Optional[List[str]] = None
    is_active: Optional[bool] = None

class CameraResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    port: int
    enabled_alerts: List[str]
    is_active: bool
    created_at: str
    updated_at: str

class CameraStatusResponse(BaseModel):
    camera_id: int
    camera_name: str
    camera_ip: str
    camera_port: int
    is_connected: bool
    last_ping_time: Optional[str]
    response_time_ms: Optional[float]
    timestamp: str

class CameraListResponse(BaseModel):
    cameras: List[CameraResponse]
    total_count: int

class CameraStatusListResponse(BaseModel):
    statuses: List[CameraStatusResponse]
    total_count: int

# Camera Alert schemas
class CameraAlertCreate(BaseModel):
    camera_id: int
    alert_type_id: int
    message: str
    severity: str = "medium"  # low, medium, high, critical

class CameraAlertResponse(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    alert_type_id: int
    alert_type_name: str
    alert_type_code: str
    message: str
    severity: str
    is_resolved: bool
    triggered_at: str
    resolved_at: Optional[str]
    created_at: str
    updated_at: str

class CameraAlertListResponse(BaseModel):
    alerts: List[CameraAlertResponse]
    total_count: int

class AlertResolution(BaseModel):
    resolved: bool = True