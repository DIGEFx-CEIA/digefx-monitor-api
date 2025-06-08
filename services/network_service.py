"""
Serviços de rede e conectividade
"""
import socket
import requests
import psutil


def is_connected(host, port=53, timeout=3):
    """Verifica se um host está conectado"""
    if host is None:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False


def get_public_ip():
    """Obtém o IP público da máquina"""
    try:
        response = requests.get("https://api.ipify.org", timeout=3)
        return response.text
    except requests.RequestException:
        return None


def get_cpu_temperature():
    """Obtém a temperatura da CPU"""
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