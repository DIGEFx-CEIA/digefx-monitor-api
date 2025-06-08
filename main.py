import os
import socket
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import psutil
from pydantic import BaseModel, Extra
from jose import JWTError, jwt
from datetime import datetime, timedelta
import requests
from sqlalchemy.orm import Session
from models import (DeviceLocation, HostStatus, User, SessionLocal, DeviceStatus, init_database,
                   Camera, CameraStatus, AlertType, CameraAlert)
from schemas import (DeviceStatusResponse, HostStatusResponse, StatusResponse, LocationListResponse, 
                    DeviceLocationResponse, AlertTypeCreate, AlertTypeResponse, CameraCreate, CameraUpdate, 
                    CameraResponse, CameraListResponse, CameraStatusResponse, CameraStatusListResponse,
                    CameraAlertCreate, CameraAlertResponse, CameraAlertListResponse, AlertResolution)
import serial
import paho.mqtt.client as mqtt
import threading
import time
from dotenv import load_dotenv
from typing import List

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "device/status"

# mqtt_client = mqtt.Client()
# mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

# App configuration
app = FastAPI()

load_dotenv()
init_database()

# JWT configuration
SECRET_KEY = "digefxsecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Security configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Serial communication configuration
SERIAL_PORT = "/dev/ttyUSB0"  # Update this according to your system
BAUD_RATE = 115200
serial_lock = threading.Lock()  # Lock for serial access

# Function to initialize the serial port
def initialize_serial():
    try:
        return serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"Error initializing serial: {e}")
        return None

ser = initialize_serial()

# Database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create default user (admin/admin)
def create_default_user():
    db = SessionLocal()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        hashed_password = pwd_context.hash("admin")
        new_user = User(username="admin", hashed_password=hashed_password)
        db.add(new_user)
        db.commit()
    db.close()

create_default_user()

# Pydantic models
class UserCredentials(BaseModel):
    username: str
    password: str

class SerialConfig(BaseModel):
    device_id: str | None = None
    relay1_time: float | None = None
    relay2_time: float | None = None
    min_voltage: float | None = None

# Authentication functions
def authenticate_user(db, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("name")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# Serial Data Reader
def read_serial_data():
    global ser
    while True:
        try:
            with serial_lock:  # Lock for safe read
                if ser and ser.in_waiting:
                    line = ser.readline().decode().strip()
                    if line and line != "ACK" and line.startswith("DEVICE_ID"):
                        process_serial_data(line)
        except serial.SerialException as e:
            print(f"Serial Exception: {e}")
            time.sleep(5)  # Wait before retrying
            ser = initialize_serial()  # Reinitialize the serial connection

# Process and store the received data
def process_serial_data(data):
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
    db.add(device_status)
    db.add(device_location)
    db.commit()
    db.close()

    # mqtt_client.publish(MQTT_TOPIC, data)

    # Send acknowledgment back to ESP32
    ser.write(b'ACK\n')
    
def is_connected(host, port=53, timeout=3):
    if host is None:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org", timeout=3)
        return response.text
    except requests.RequestException:
        return None    
    
def get_cpu_temperature():
    if not hasattr(psutil, "sensors_temperatures"):
        return None

    temps = psutil.sensors_temperatures()
    if not temps:
        return None

    # Sensores preferenciais por arquitetura
    cpu_sensor_keys = ["coretemp", "k10temp", "cpu_thermal", "acpitz"]

    for key in cpu_sensor_keys:
        if key in temps:
            for entry in temps[key]:
                if entry.label in ("Tctl", "Tdie", "Package id 0", "Core 0", ""):
                    return entry.current

    # Fallback: primeira temperatura válida
    for sensor_entries in temps.values():
        for entry in sensor_entries:
            if hasattr(entry, "current"):
                return entry.current

    return None

def monitor_host():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            # IP do host
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)

            db = SessionLocal()
            status = HostStatus(
                host_ip=ip_address,
                public_ip=get_public_ip(),
                cpu_usage=cpu,
                ram_usage=ram,
                disk_usage=disk,
                online=is_connected("8.8.8.8"),
                temperature=get_cpu_temperature(),
                timestamp=datetime.utcnow(),
            )
            db.add(status)
            db.commit()
            db.close()

        except Exception as e:
            print(f"[HOST MONITOR] Erro: {e}")

        time.sleep(10)

def monitor_cameras():
    """Monitor all dynamic cameras connectivity"""
    while True:
        try:
            db = SessionLocal()
            
            # Get all active cameras from database
            cameras = db.query(Camera).filter(Camera.is_active == True).all()
            
            # Monitor each camera dynamically
            for camera in cameras:
                start_time = time.time()
                camera_connected = is_connected(camera.ip_address, camera.port)
                response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                
                # Save camera status to database
                camera_status = CameraStatus(
                    camera_id=camera.id,
                    is_connected=camera_connected,
                    last_ping_time=datetime.utcnow() if camera_connected else None,
                    response_time_ms=response_time if camera_connected else None,
                    timestamp=datetime.utcnow(),
                )
                db.add(camera_status)
            
            db.commit()
            db.close()
            
        except Exception as e:
            print(f"[CAMERA MONITOR] Error: {e}")
            if 'db' in locals():
                db.rollback()
                db.close()

        time.sleep(10)

# Start serial reading in background
threading.Thread(target=read_serial_data, daemon=True).start()
# Start host monitoring in background
threading.Thread(target=monitor_host, daemon=True).start()
threading.Thread(target=monitor_cameras, daemon=True).start()

# Login route
@app.post("/login")
def login(credentials: UserCredentials, db: Session = Depends(get_db)):
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"name": user.username})
    return {"access_token": access_token, "token_type": "bearer", "name": user.username, "id": user.id}

# Register route (protected)
@app.post("/register")
def register(credentials: UserCredentials, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == credentials.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = pwd_context.hash(credentials.password)
    new_user = User(username=credentials.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": f"User '{credentials.username}' successfully registered."}

# Serial configuration route (protected)
@app.post("/configure")
def configure(config: SerialConfig, current_user: User = Depends(get_current_user)):
    config_dict = config.model_dump(exclude_unset=True, exclude_none=True)
    with serial_lock:  # Lock for safe write
        for key, value in config_dict.items():
            ser.write(f"{key.upper()}:{value}\n".encode())
            response = ser.readline().decode().strip()
            if response != "ACK":
                raise HTTPException(status_code=500, detail=f"Failed to set {key}")
    return {"status": "Configuration sent", **config_dict}

# Protected route to fetch current device status
@app.get("/status", response_model=StatusResponse)
def get_device_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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

# Protected route to fetch device locations for current day
@app.get("/locations/today", response_model=LocationListResponse)
def get_today_locations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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

# Alert Types Management
@app.get("/alert-types", response_model=List[AlertTypeResponse])
def get_alert_types(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all available alert types"""
    alert_types = db.query(AlertType).filter(AlertType.is_active == True).all()
    return [
        AlertTypeResponse(
            id=alert.id,
            code=alert.code,
            name=alert.name,
            description=alert.description,
            is_active=alert.is_active,
            created_at=alert.created_at.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) for alert in alert_types
    ]

@app.post("/alert-types", response_model=AlertTypeResponse)
def create_alert_type(alert_type: AlertTypeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new alert type"""
    # Check if alert type already exists
    existing_alert = db.query(AlertType).filter(AlertType.code == alert_type.code).first()
    if existing_alert:
        raise HTTPException(status_code=400, detail="Alert type with this code already exists")
    
    new_alert = AlertType(
        code=alert_type.code,
        name=alert_type.name,
        description=alert_type.description,
        created_at=datetime.utcnow()
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    
    return AlertTypeResponse(
        id=new_alert.id,
        code=new_alert.code,
        name=new_alert.name,
        description=new_alert.description,
        is_active=new_alert.is_active,
        created_at=new_alert.created_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )

# Camera Management
@app.get("/cameras", response_model=CameraListResponse)
def get_cameras(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all cameras"""
    cameras = db.query(Camera).all()
    camera_responses = [
        CameraResponse(
            id=camera.id,
            name=camera.name,
            ip_address=camera.ip_address,
            port=camera.port,
            enabled_alerts=camera.enabled_alerts or [],
            is_active=camera.is_active,
            created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
            updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) for camera in cameras
    ]
    
    return CameraListResponse(cameras=camera_responses, total_count=len(camera_responses))

@app.post("/cameras", response_model=CameraResponse)
def create_camera(camera: CameraCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new camera"""
    # Check if camera name already exists
    existing_camera = db.query(Camera).filter(Camera.name == camera.name).first()
    if existing_camera:
        raise HTTPException(status_code=400, detail="Camera with this name already exists")
    
    # Validate alert types
    if camera.enabled_alerts:
        valid_alerts = db.query(AlertType).filter(AlertType.code.in_(camera.enabled_alerts)).all()
        if len(valid_alerts) != len(camera.enabled_alerts):
            raise HTTPException(status_code=400, detail="Some alert types are invalid")
    
    new_camera = Camera(
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_camera)
    db.commit()
    db.refresh(new_camera)
    
    return CameraResponse(
        id=new_camera.id,
        name=new_camera.name,
        ip_address=new_camera.ip_address,
        port=new_camera.port,
        enabled_alerts=new_camera.enabled_alerts or [],
        is_active=new_camera.is_active,
        created_at=new_camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=new_camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )

@app.get("/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get a specific camera"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts or [],
        is_active=camera.is_active,
        created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )

@app.put("/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: int, camera_update: CameraUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Update a camera"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Check for name conflicts if name is being updated
    if camera_update.name and camera_update.name != camera.name:
        existing_camera = db.query(Camera).filter(Camera.name == camera_update.name).first()
        if existing_camera:
            raise HTTPException(status_code=400, detail="Camera with this name already exists")
    
    # Validate alert types if being updated
    if camera_update.enabled_alerts is not None:
        valid_alerts = db.query(AlertType).filter(AlertType.code.in_(camera_update.enabled_alerts)).all()
        if len(valid_alerts) != len(camera_update.enabled_alerts):
            raise HTTPException(status_code=400, detail="Some alert types are invalid")
    
    # Update camera fields
    update_data = camera_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
    
    camera.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(camera)
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts or [],
        is_active=camera.is_active,
        created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )

@app.delete("/cameras/{camera_id}")
def delete_camera(camera_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a camera"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    db.delete(camera)
    db.commit()
    return {"message": "Camera deleted successfully"}

# Camera Status Monitoring
@app.get("/cameras/status", response_model=CameraStatusListResponse)
def get_cameras_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get latest status for all cameras"""
    # Get the latest status for each camera
    subquery = db.query(
        CameraStatus.camera_id,
        db.func.max(CameraStatus.timestamp).label('latest_timestamp')
    ).group_by(CameraStatus.camera_id).subquery()
    
    latest_statuses = db.query(CameraStatus).join(
        subquery,
        db.and_(
            CameraStatus.camera_id == subquery.c.camera_id,
            CameraStatus.timestamp == subquery.c.latest_timestamp
        )
    ).all()
    
    status_responses = []
    for status in latest_statuses:
        camera = db.query(Camera).filter(Camera.id == status.camera_id).first()
        if camera:
            status_responses.append(CameraStatusResponse(
                camera_id=camera.id,
                camera_name=camera.name,
                camera_ip=camera.ip_address,
                camera_port=camera.port,
                is_connected=status.is_connected,
                last_ping_time=status.last_ping_time.strftime("%Y-%m-%d %H:%M:%S GMT") if status.last_ping_time else None,
                response_time_ms=status.response_time_ms,
                timestamp=status.timestamp.strftime("%Y-%m-%d %H:%M:%S GMT")
            ))
    
    return CameraStatusListResponse(statuses=status_responses, total_count=len(status_responses))

# Camera Alerts Management
@app.post("/camera-alerts", response_model=CameraAlertResponse)
def create_camera_alert(alert: CameraAlertCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new camera alert (typically called by AI detection system)"""
    # Validate camera exists
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Validate alert type exists
    alert_type = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
    if not alert_type:
        raise HTTPException(status_code=404, detail="Alert type not found")
    
    # Check if alert type is enabled for this camera
    if alert.alert_type_code not in (camera.enabled_alerts or []):
        raise HTTPException(status_code=400, detail="Alert type not enabled for this camera")
    
    new_alert = CameraAlert(
        camera_id=alert.camera_id,
        alert_type_code=alert.alert_type_code,
        detection_timestamp=datetime.utcnow(),
        confidence_score=alert.confidence_score,
        alert_metadata=alert.alert_metadata
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    
    return CameraAlertResponse(
        id=new_alert.id,
        camera_id=new_alert.camera_id,
        camera_name=camera.name,
        alert_type_code=new_alert.alert_type_code,
        alert_type_name=alert_type.name,
        detection_timestamp=new_alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
        confidence_score=new_alert.confidence_score,
        metadata=new_alert.alert_metadata,
        resolved=new_alert.resolved,
        resolved_at=new_alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if new_alert.resolved_at else None,
        resolved_by=new_alert.resolved_by
    )

@app.get("/camera-alerts", response_model=CameraAlertListResponse)
def get_camera_alerts(
    camera_id: int = None,
    alert_type: str = None,
    resolved: bool = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get camera alerts with optional filters"""
    query = db.query(CameraAlert)
    
    if camera_id:
        query = query.filter(CameraAlert.camera_id == camera_id)
    if alert_type:
        query = query.filter(CameraAlert.alert_type_code == alert_type)
    if resolved is not None:
        query = query.filter(CameraAlert.resolved == resolved)
    
    alerts = query.order_by(CameraAlert.detection_timestamp.desc()).limit(limit).all()
    
    alert_responses = []
    for alert in alerts:
        camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
        alert_type_obj = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
        
        alert_responses.append(CameraAlertResponse(
            id=alert.id,
            camera_id=alert.camera_id,
            camera_name=camera.name if camera else "Unknown",
            alert_type_code=alert.alert_type_code,
            alert_type_name=alert_type_obj.name if alert_type_obj else "Unknown",
            detection_timestamp=alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
            confidence_score=alert.confidence_score,
            metadata=alert.alert_metadata,
            resolved=alert.resolved,
            resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
            resolved_by=alert.resolved_by
        ))
    
    return CameraAlertListResponse(alerts=alert_responses, total_count=len(alert_responses))

@app.put("/camera-alerts/{alert_id}/resolve", response_model=CameraAlertResponse)
def resolve_camera_alert(alert_id: int, resolution: AlertResolution, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resolve or unresolve a camera alert"""
    alert = db.query(CameraAlert).filter(CameraAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.resolved = resolution.resolved
    if resolution.resolved:
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = current_user.id
    else:
        alert.resolved_at = None
        alert.resolved_by = None
    
    db.commit()
    db.refresh(alert)
    
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    alert_type = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
    
    return CameraAlertResponse(
        id=alert.id,
        camera_id=alert.camera_id,
        camera_name=camera.name if camera else "Unknown",
        alert_type_code=alert.alert_type_code,
        alert_type_name=alert_type.name if alert_type else "Unknown",
        detection_timestamp=alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
        confidence_score=alert.confidence_score,
        metadata=alert.alert_metadata,
        resolved=alert.resolved,
        resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
        resolved_by=alert.resolved_by
    )
