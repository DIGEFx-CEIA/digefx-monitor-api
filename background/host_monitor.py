"""
Monitor de status do host em background
"""
import socket
import psutil
import threading
import time
from datetime import datetime

from services.network_service import is_connected, get_public_ip, get_cpu_temperature
from models import HostStatus, SessionLocal


def monitor_host():
    """Monitora o status do host"""
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent

            # IP do host
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)

            db = SessionLocal()
            try:
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
            finally:
                db.close()

        except Exception as e:
            print(f"[HOST MONITOR] Erro: {e}")

        time.sleep(10)


def start_host_monitoring():
    """Inicia o monitoramento do host em thread separada"""
    threading.Thread(target=monitor_host, daemon=True).start()
    print("Host monitoring started") 