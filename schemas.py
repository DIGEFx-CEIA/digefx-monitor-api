from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from models import CameraType


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
    icon: Optional[str] = "Warning"  # Material-UI icon name
    color: Optional[str] = "#ff9800"  # Hex color for the alert
    severity: str = "medium"  # low, medium, high, critical

class AlertTypeResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    severity: str
    is_active: bool
    created_at: str
    updated_at: str

class AlertTypeListResponse(BaseModel):
    alert_types: List[AlertTypeResponse]
    total_count: int

# Camera schemas
class CameraCreate(BaseModel):
    name: str
    ip_address: str
    port: int = 80
    camera_type: CameraType = CameraType.INTERNAL
    enabled_alerts: List[str] = []  # List of alert type codes

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    camera_type: Optional[CameraType] = None
    enabled_alerts: Optional[List[str]] = None
    is_active: Optional[bool] = None

class CameraResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    port: int
    camera_type: str
    enabled_alerts: List[str]
    is_active: bool
    created_at: str
    updated_at: str

class CameraStatusResponse(BaseModel):
    camera_id: int
    camera_name: str
    camera_ip: str
    camera_port: int
    camera_type: str
    is_connected: bool
    is_active: bool
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
    alert_metadata: Optional[Dict[str, Any]] = None

class CameraAlertResponse(BaseModel):
    id: int
    camera_id: int
    camera_name: str
    alert_type_id: int
    alert_type_name: str
    alert_type_code: str
    alert_metadata: Optional[Dict[str, Any]] = None
    resolved: bool
    resolved_at: Optional[str]
    resolved_by: Optional[str]
    triggered_at: str
    severity: Optional[str]
class CameraAlertListResponse(BaseModel):
    alerts: List[CameraAlertResponse]
    total_count: int

class AlertResolution(BaseModel):
    resolved: bool = True