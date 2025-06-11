"""
Monitor de conectividade de câmeras em background
"""
import threading
import time
from datetime import datetime

from services.network_service import is_connected
from models import Camera, CameraStatus, SessionLocal


def monitor_cameras():
    """Monitora todas as câmeras dinâmicas de conectividade"""
    while True:
        try:
            db = SessionLocal()
            
            # Get all active cameras from database
            cameras = db.query(Camera).filter(Camera.is_active == True).all()
            
            # Monitor each camera dynamically
            for camera in cameras:
                start_time = time.time()
                camera_connected = is_connected(camera.ip_address, camera.port)
                # Convert to milliseconds and round to 2 decimal places
                response_time = round((time.time() - start_time) * 1000, 2)  
                
                
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


def start_camera_monitoring():
    """Inicia o monitoramento de câmeras em thread separada"""
    threading.Thread(target=monitor_cameras, daemon=True).start()
    print("Camera monitoring started") 