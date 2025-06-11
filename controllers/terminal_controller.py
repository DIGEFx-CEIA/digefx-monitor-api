"""
Controller para acesso seguro ao terminal do host
"""
import os
import time
import subprocess
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from config.security import get_current_user

router = APIRouter(prefix="/terminal", tags=["terminal"])

# Obter caminho do docker-compose da variável de ambiente
DOCKER_COMPOSE_PATH = os.getenv('DOCKER_COMPOSE_PATH', 'docker')

# Comandos permitidos organizados por categoria
ALLOWED_COMMANDS = {
    'docker': {
        'ps': ['docker', 'ps'],
        'stats': ['docker', 'stats', '--no-stream'],
        'logs': ['docker', 'logs', '--tail', '50'],
        'restart': ['docker', 'restart'],
        'stop': ['docker', 'stop'],
        'start': ['docker', 'start'],
        'images': ['docker', 'images'],
        'compose-ps': [DOCKER_COMPOSE_PATH, 'compose', 'ps'] if DOCKER_COMPOSE_PATH == 'docker' else [DOCKER_COMPOSE_PATH, 'ps'],
        'compose-logs': [DOCKER_COMPOSE_PATH, 'compose', 'logs', '--tail', '50'] if DOCKER_COMPOSE_PATH == 'docker' else [DOCKER_COMPOSE_PATH, 'logs', '--tail', '50'],
        'compose-up': [DOCKER_COMPOSE_PATH, 'compose', 'up', '-d'] if DOCKER_COMPOSE_PATH == 'docker' else [DOCKER_COMPOSE_PATH, 'up', '-d'],
        'compose-down': [DOCKER_COMPOSE_PATH, 'compose', 'down'] if DOCKER_COMPOSE_PATH == 'docker' else [DOCKER_COMPOSE_PATH, 'down'],
        'compose-restart': [DOCKER_COMPOSE_PATH, 'compose', 'restart'] if DOCKER_COMPOSE_PATH == 'docker' else [DOCKER_COMPOSE_PATH, 'restart'],
    },
    'system': {
        'top': ['top', '-b', '-n', '1'],
        'df': ['df', '-h'],
        'free': ['free', '-h'],
        'uptime': ['uptime'],
        'whoami': ['whoami'],
        'pwd': ['pwd'],
        'ls': ['ls', '-la'],
        'ps': ['ps', 'aux'],
        'date': ['date'],
        'uname': ['uname', '-a'],
    },
    'network': {
        'ping': ['ping', '-c', '4'],
        'netstat': ['netstat', '-tuln'],
        'ip': ['ip', 'addr', 'show'],
        'wget-test': ['wget', '--spider', '--timeout=10'],
        'curl-test': ['curl', '-I', '--max-time', '10'],
    },
    'files': {
        'ls': ['ls', '-la'],
        'pwd': ['pwd'],
        'find': ['find', '.', '-name'],
        'cat': ['cat'],
        'tail': ['tail', '-n', '20'],
        'head': ['head', '-n', '20'],
    }
}

class CommandRequest(BaseModel):
    category: str
    command: str
    args: List[str] = []

class CommandResponse(BaseModel):
    success: bool
    output: str
    error: str = ""
    execution_time: float
    command_executed: str

def execute_command_on_host(command_list: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """
    Executa comando no host usando nsenter para acessar os namespaces do host
    """
    # Para comandos docker compose, incluir mudança de diretório
    docker_compose_commands = ['compose-ps', 'compose-logs', 'compose-up', 'compose-down', 'compose-restart']
    
    # Verificar se é um comando docker-compose
    is_compose_command = (
        len(command_list) >= 2 and 
        (
            (command_list[0] == 'docker' and command_list[1] == 'compose') or
            (command_list[0] == DOCKER_COMPOSE_PATH and DOCKER_COMPOSE_PATH != 'docker')
        )
    )
    
    if is_compose_command:
        # Construir comando que muda para o diretório correto
        project_dir = os.getenv('DOCKER_COMPOSE_PROJECT_DIR', '/media/ratacheski/Storage/Ceia/DIGEFx/fonte/digefx-power-management')
        command_str = f"cd {project_dir} && {' '.join(command_list)}"
        nsenter_command = ['nsenter', '-t', '1', '-m', '-p', '-n', '-u', '-i', 'bash', '-c', command_str]
    else:
        # Usar nsenter para todos os outros comandos
        nsenter_command = ['nsenter', '-t', '1', '-m', '-p', '-n', '-u', '-i'] + command_list
    
    return subprocess.run(
        nsenter_command,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/",
        shell=False
    )

@router.post("/execute", response_model=CommandResponse)
async def execute_command(
    request: CommandRequest,
    current_user = Depends(get_current_user)
):
    """Executa comando seguro no host"""
    
    # Verificar se o comando está na lista permitida
    if request.category not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail="Categoria de comando não permitida")
    
    if request.command not in ALLOWED_COMMANDS[request.category]:
        raise HTTPException(status_code=400, detail="Comando não permitido")
    
    base_command = ALLOWED_COMMANDS[request.category][request.command].copy()
    
    # Adicionar argumentos seguros
    if request.args:
        # Validar argumentos para evitar injection
        safe_args = [arg for arg in request.args if is_safe_arg(arg)]
        base_command.extend(safe_args)
    
    command_str = ' '.join(base_command)
    
    try:
        start_time = time.time()
        
        # Executar comando no host
        result = execute_command_on_host(base_command)
        
        execution_time = time.time() - start_time
        
        return CommandResponse(
            success=result.returncode == 0,
            output=result.stdout if result.stdout else "Comando executado com sucesso (sem saída)",
            error=result.stderr,
            execution_time=execution_time,
            command_executed=f"[HOST] {command_str}"
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Comando expirou (timeout 30s)")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Comando não encontrado no sistema do host")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na execução no host: {str(e)}")

def is_safe_arg(arg: str) -> bool:
    """Valida se o argumento é seguro"""
    if not arg or len(arg) > 100:  # Limitar tamanho
        return False
        
    dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '{', '}', '<', '>', '\n', '\r', '&&', '||']
    dangerous_keywords = ['rm', 'del', 'format', 'sudo', 'su', 'passwd', 'chmod']
    
    # Verificar caracteres perigosos
    for char in dangerous_chars:
        if char in arg:
            return False
    
    # Verificar palavras-chave perigosas
    for keyword in dangerous_keywords:
        if keyword.lower() in arg.lower():
            return False
            
    return True

@router.get("/commands")
async def get_available_commands(current_user = Depends(get_current_user)):
    """Retorna lista de comandos disponíveis"""
    return {
        "categories": ALLOWED_COMMANDS,
        "total_commands": sum(len(commands) for commands in ALLOWED_COMMANDS.values()),
        "security_info": {
            "timeout": "30 segundos",
            "working_directory": "host root (/)",
            "shell_disabled": True,
            "argument_validation": True,
            "execution_context": "HOST SYSTEM",
            "docker_compose_path": DOCKER_COMPOSE_PATH,
            "project_directory": os.getenv('DOCKER_COMPOSE_PROJECT_DIR', '/media/ratacheski/Storage/Ceia/DIGEFx/fonte/digefx-power-management')
        }
    }

@router.get("/system-info")
async def get_system_info(current_user = Depends(get_current_user)):
    """Retorna informações básicas do sistema HOST"""
    try:
        # Informações básicas do sistema HOST
        commands = {
            "hostname": ["hostname"],
            "uptime": ["uptime"],
            "whoami": ["whoami"],
            "date": ["date"],
            "uname": ["uname", "-a"]
        }
        
        info = {}
        for key, cmd in commands.items():
            try:
                result = execute_command_on_host(cmd, timeout=5)
                if result.returncode == 0:
                    info[key] = result.stdout.strip()
                else:
                    info[key] = "N/A"
            except:
                info[key] = "N/A"
        
        info["execution_context"] = "HOST SYSTEM"
        return info
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter informações do sistema HOST: {str(e)}") 