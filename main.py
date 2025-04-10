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
from models import CameraStatus, HostStatus, User, SessionLocal, DeviceStatus
from schemas import CameraStatusResponse, DeviceStatusResponse, HostStatusResponse, StatusResponse
import serial
import paho.mqtt.client as mqtt
import threading
import time
from dotenv import load_dotenv

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "device/status"

# mqtt_client = mqtt.Client()
# mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

# App configuration
app = FastAPI()
load_dotenv()

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

class SerialConfig(BaseModel, extra=Extra.forbid):
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
                    if line and line != "ACK":
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
    )

    db = SessionLocal()
    db.add(device_status)
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
                temperature=get_cpu_temperature()
            )
            db.add(status)
            db.commit()
            db.close()

        except Exception as e:
            print(f"[HOST MONITOR] Erro: {e}")

        time.sleep(10)

def monitor_cameras():
    while True:
        try:
            camera1_host = os.getenv('CAMERA_1_HOST')
            camera1_connected = is_connected(camera1_host,80)
            camera2_host = os.getenv('CAMERA_2_HOST')
            camera2_connected = is_connected(camera2_host,80)
            camera3_host = os.getenv('CAMERA_3_HOST')
            camera3_connected = is_connected(camera3_host,80)
            camera4_host = os.getenv('CAMERA_4_HOST')
            camera4_connected = is_connected(camera4_host,80)
            # Save camera status to database
            db = SessionLocal()
            camera_status = CameraStatus(
                camera1_ip=camera1_host,
                camera1_connected=camera1_connected,
                camera2_ip=camera2_host,
                camera2_connected=camera2_connected,
                camera3_ip=camera3_host,
                camera3_connected=camera3_connected,
                camera4_ip=camera4_host,
                camera4_connected=camera4_connected,
            )
            db.add(camera_status)
            db.commit()
            db.close()
        except Exception as e:
            print(f"[CAMERA MONITOR] Erro: {e}")

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
    config_dict = config.dict(exclude_none=True)
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
    camera_status = db.query(CameraStatus).order_by(CameraStatus.timestamp.desc()).first()
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
            timestamp=device_status.timestamp
        ) if device_status else None,
        "host_status": HostStatusResponse(
            host_ip=host_status.host_ip,
            public_ip=host_status.public_ip,
            cpu_usage=host_status.cpu_usage,
            ram_usage=host_status.ram_usage,
            disk_usage=host_status.disk_usage,
            temperature=host_status.temperature,
            online=host_status.online,
            timestamp=host_status.timestamp
        ) if host_status else None,
        "camera_status": CameraStatusResponse(
            camera1_ip=camera_status.camera1_ip,
            camera1_connected=camera_status.camera1_connected,
            camera2_ip=camera_status.camera2_ip,
            camera2_connected=camera_status.camera2_connected,
            camera3_ip=camera_status.camera3_ip,
            camera3_connected=camera_status.camera3_connected,
            camera4_ip=camera_status.camera4_ip,
            camera4_connected=camera_status.camera4_connected,
            timestamp=camera_status.timestamp
        ) if camera_status else None
    }
