"""
Gerenciador centralizado de comunicação serial
Resolve problemas de concorrência com um único thread de leitura/escrita
SOLUÇÃO: Usa file descriptor direto em vez de pySerial (evita reset do ESP32)
"""
import threading
import queue
import time
import logging
from datetime import datetime
from typing import Callable, Dict, Optional, Any
from enum import Enum

from config import app_config
from .serial_wrapper import SerialFileDescriptor

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Tipos de mensagens recebidas do ESP32"""
    STATUS_DATA = "STATUS_DATA"      # DEVICE_ID:... (dados do ESP)
    ACK = "ACK"                      # Confirmação de comando
    ESP32_READY = "ESP32_READY"      # ESP32 inicializado
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"  # Timeout de heartbeat
    DEBUG = "DEBUG"                  # Mensagens de debug
    UNKNOWN = "UNKNOWN"              # Mensagem não reconhecida


class SerialManager:
    """
    Gerenciador centralizado de comunicação serial
    - Thread único de leitura
    - Fila para envio de comandos
    - Sistema de callbacks para processar respostas
    - Thread-safe e robusto a erros
    """
    
    def __init__(self, port: str = None, baudrate: int = None):
        self.port = port or app_config.SERIAL_PORT
        self.baudrate = baudrate or app_config.BAUD_RATE
        
        # Conexão serial (usando wrapper de file descriptor)
        self._serial: Optional[SerialFileDescriptor] = None
        self._serial_lock = threading.Lock()
        
        # Filas de controle
        self._command_queue = queue.Queue()
        self._response_queue = queue.Queue(maxsize=100)
        
        # Callbacks registrados por tipo de mensagem
        self._callbacks: Dict[MessageType, list[Callable]] = {
            msg_type: [] for msg_type in MessageType
        }
        
        # Controle de threads
        self._running = False
        self._read_thread: Optional[threading.Thread] = None
        self._write_thread: Optional[threading.Thread] = None
        self._callback_thread: Optional[threading.Thread] = None
        
        # Estatísticas
        self._stats = {
            'messages_received': 0,
            'messages_sent': 0,
            'errors': 0,
            'invalid_chars': 0,
            'boot_garbage_filtered': 0
        }
        
        # Timeout para aguardar respostas
        self._response_timeout = 2.0
        
        # Ignorar mensagens garbage nos primeiros segundos
        self._ignore_garbage_until = 0
        self._boot_grace_period = 3.0  # Período de graça para mensagens residuais
        
    def start(self):
        """Inicia o gerenciador serial"""
        if self._running:
            logger.warning("SerialManager já está em execução")
            return
            
        logger.info(f"🚀 Iniciando SerialManager em {self.port} @ {self.baudrate}")
        
        # Inicializar conexão serial
        if not self._initialize_serial():
            raise Exception("Falha ao inicializar porta serial")
        
        # Iniciar threads
        self._running = True
        
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True, name="SerialRead")
        self._write_thread = threading.Thread(target=self._write_loop, daemon=True, name="SerialWrite")
        self._callback_thread = threading.Thread(target=self._callback_loop, daemon=True, name="SerialCallback")
        
        self._read_thread.start()
        self._write_thread.start()
        self._callback_thread.start()
        
        logger.info("✅ SerialManager iniciado com sucesso")
        
    def stop(self):
        """Para o gerenciador serial"""
        if not self._running:
            return
            
        logger.info("🛑 Parando SerialManager...")
        
        self._running = False
        
        # Aguardar threads finalizarem
        if self._read_thread:
            self._read_thread.join(timeout=2)
        if self._write_thread:
            self._write_thread.join(timeout=2)
        if self._callback_thread:
            self._callback_thread.join(timeout=2)
            
        # Fechar conexão serial
        if self._serial and self._serial.is_open:
            self._serial.close()
            
        logger.info("✅ SerialManager parado")
        
    def _initialize_serial(self) -> bool:
        """Inicializa a conexão serial"""
        try:
            if self._serial and self._serial.is_open:
                return True
            
            # ✅ SOLUÇÃO: Usar file descriptor direto (não usa pySerial!)
            # Isso evita que pySerial force DTR/RTS ao abrir porta
            logger.info(f"🔧 Inicializando wrapper de serial (file descriptor)...")
            
            self._serial = SerialFileDescriptor(self.port, self.baudrate)
            self._serial.open()
            
            logger.info(f"✅ Porta serial {self.port} aberta via file descriptor")
            logger.info(f"✅ ESP32 NÃO resetou (método file descriptor)")
            
            # Limpar buffer inicial (se houver)
            self._serial.reset_input_buffer()
            logger.info(f"🗑️ Buffer inicial limpo")
            
            # Período de graça reduzido (não houve boot)
            self._ignore_garbage_until = time.time() + 3.0
            
            logger.info(f"✅ Comunicação serial estabelecida SEM reset!")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar serial: {e}")
            self._serial = None
            return False
            
    def _reconnect_serial(self):
        """Tenta reconectar a porta serial"""
        logger.warning("🔄 Tentando reconectar porta serial...")
        
        if self._serial:
            try:
                self._serial.close()
            except:
                pass
            self._serial = None
            
        time.sleep(2)
        self._initialize_serial()
        
    def _read_loop(self):
        """Thread de leitura contínua da porta serial"""
        logger.info("📖 Thread de leitura iniciada")
        
        buffer = ""
        
        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    self._reconnect_serial()
                    continue
                    
                # Ler bytes disponíveis
                if self._serial.in_waiting > 0:
                    # Ler com tratamento de erros
                    try:
                        data = self._serial.read(self._serial.in_waiting)
                        # Decodificar com tratamento de caracteres inválidos
                        text = data.decode('utf-8', errors='ignore')
                        
                        # Contar caracteres inválidos
                        if len(data) != len(text.encode('utf-8')):
                            self._stats['invalid_chars'] += 1
                            logger.debug("⚠️ Caracteres inválidos ignorados")
                            
                        buffer += text
                        
                    except UnicodeDecodeError as e:
                        self._stats['invalid_chars'] += 1
                        logger.warning(f"⚠️ Erro de decodificação: {e}")
                        continue
                    
                    # Processar linhas completas
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line:
                            self._process_received_message(line)
                            self._stats['messages_received'] += 1
                            
                else:
                    time.sleep(0.01)  # Pequena pausa se não há dados
                    
            except serial.SerialException as e:
                logger.error(f"❌ Exceção serial na leitura: {e}")
                self._stats['errors'] += 1
                self._reconnect_serial()
                
            except Exception as e:
                logger.error(f"❌ Erro inesperado na leitura: {e}")
                self._stats['errors'] += 1
                time.sleep(0.1)
                
        logger.info("📖 Thread de leitura finalizada")
        
    def _write_loop(self):
        """Thread de escrita de comandos"""
        logger.info("✍️ Thread de escrita iniciada")
        
        while self._running:
            try:
                # Pegar comando da fila (blocking com timeout)
                try:
                    command_data = self._command_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                    
                command = command_data['command']
                callback = command_data.get('callback')
                
                # Enviar comando
                if self._send_command_internal(command):
                    self._stats['messages_sent'] += 1
                    
                    # Chamar callback de sucesso se fornecido
                    if callback:
                        callback(True, None)
                else:
                    self._stats['errors'] += 1
                    
                    # Chamar callback de falha
                    if callback:
                        callback(False, "Falha ao enviar comando")
                        
            except Exception as e:
                logger.error(f"❌ Erro na thread de escrita: {e}")
                self._stats['errors'] += 1
                
        logger.info("✍️ Thread de escrita finalizada")
        
    def _callback_loop(self):
        """Thread para processar callbacks de forma assíncrona"""
        logger.info("📞 Thread de callbacks iniciada")
        
        while self._running:
            try:
                # Pegar mensagem da fila de respostas
                try:
                    message = self._response_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                    
                msg_type = message['type']
                data = message['data']
                
                # Executar callbacks registrados
                callbacks = self._callbacks.get(msg_type, [])
                for callback in callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"❌ Erro ao executar callback: {e}")
                        
            except Exception as e:
                logger.error(f"❌ Erro na thread de callbacks: {e}")
                
        logger.info("📞 Thread de callbacks finalizada")
        
    def _send_command_internal(self, command: str) -> bool:
        """Envia comando para o ESP32 (uso interno)"""
        try:
            if not self._serial or not self._serial.is_open:
                logger.warning("⚠️ Porta serial não está aberta")
                return False
                
            # Adicionar newline se necessário
            if not command.endswith('\n'):
                command += '\n'
                
            # Enviar comando
            self._serial.write(command.encode('utf-8'))
            self._serial.flush()
            
            logger.debug(f"📤 Comando enviado: {command.strip()}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar comando: {e}")
            return False
            
    def _process_received_message(self, message: str):
        """Processa mensagem recebida e determina o tipo"""
        
        # Se estamos no período de graça do boot, filtrar garbage
        if time.time() < self._ignore_garbage_until:
            # Verificar se é uma mensagem válida (começando com palavra conhecida)
            valid_starts = ['DEVICE_ID:', 'ACK', 'ESP32_READY', 'HEARTBEAT_TIMEOUT', 
                          'DEBUG:', '===', 'ESP32 DIGEFX']
            
            is_valid = any(message.startswith(start) for start in valid_starts)
            
            if not is_valid:
                # Provavelmente é garbage do boot, ignorar silenciosamente
                self._stats['boot_garbage_filtered'] += 1
                logger.debug(f"🗑️ Garbage de boot filtrado: {message[:30]}...")
                return
        
        logger.debug(f"📥 Recebido: {message}")
        
        # Determinar tipo da mensagem
        msg_type = self._identify_message_type(message)
        
        # Adicionar à fila de processamento
        try:
            self._response_queue.put({
                'type': msg_type,
                'data': message,
                'timestamp': datetime.utcnow()
            }, block=False)
        except queue.Full:
            logger.warning("⚠️ Fila de respostas cheia, descartando mensagem")
            
    def _identify_message_type(self, message: str) -> MessageType:
        """Identifica o tipo da mensagem recebida"""
        if message == "ACK":
            return MessageType.ACK
        elif message == "ESP32_READY":
            return MessageType.ESP32_READY
        elif message == "HEARTBEAT_TIMEOUT":
            return MessageType.HEARTBEAT_TIMEOUT
        elif message.startswith("DEVICE_ID:"):
            return MessageType.STATUS_DATA
        elif message.startswith("DEBUG:"):
            return MessageType.DEBUG
        else:
            return MessageType.UNKNOWN
            
    # === API Pública ===
    
    def send_command(self, command: str, callback: Optional[Callable] = None):
        """
        Envia comando para o ESP32 de forma assíncrona
        
        Args:
            command: Comando a ser enviado
            callback: Callback(success: bool, error: str) chamado após envio
        """
        self._command_queue.put({
            'command': command,
            'callback': callback
        })
        
    def send_command_sync(self, command: str, wait_for_ack: bool = True, timeout: float = 2.0) -> bool:
        """
        Envia comando e aguarda confirmação (bloqueante)
        
        Args:
            command: Comando a ser enviado
            wait_for_ack: Se deve aguardar ACK
            timeout: Tempo máximo de espera
            
        Returns:
            True se comando foi enviado (e ACK recebido se wait_for_ack=True)
        """
        if not wait_for_ack:
            # Envio simples sem espera
            success = [False]
            
            def callback(ok, error):
                success[0] = ok
                
            self.send_command(command, callback)
            
            # Aguardar envio
            time.sleep(0.1)
            return success[0]
            
        else:
            # Envio com espera de ACK
            ack_received = threading.Event()
            success = [False]
            
            def ack_callback(data):
                success[0] = True
                ack_received.set()
                
            # Registrar callback temporário para ACK
            self.register_callback(MessageType.ACK, ack_callback)
            
            # Enviar comando
            self.send_command(command)
            
            # Aguardar ACK
            got_ack = ack_received.wait(timeout=timeout)
            
            # Remover callback temporário
            self.unregister_callback(MessageType.ACK, ack_callback)
            
            return got_ack and success[0]
            
    def register_callback(self, msg_type: MessageType, callback: Callable):
        """
        Registra callback para processar mensagens de um tipo específico
        
        Args:
            msg_type: Tipo de mensagem
            callback: Função callback(data: str)
        """
        if callback not in self._callbacks[msg_type]:
            self._callbacks[msg_type].append(callback)
            logger.debug(f"📝 Callback registrado para {msg_type.value}")
            
    def unregister_callback(self, msg_type: MessageType, callback: Callable):
        """Remove callback registrado"""
        if callback in self._callbacks[msg_type]:
            self._callbacks[msg_type].remove(callback)
            logger.debug(f"📝 Callback removido para {msg_type.value}")
            
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da comunicação serial"""
        return self._stats.copy()
        
    def is_running(self) -> bool:
        """Verifica se o gerenciador está em execução"""
        return self._running


# Instância global do SerialManager
_serial_manager: Optional[SerialManager] = None


def get_serial_manager() -> SerialManager:
    """Obtém a instância global do SerialManager"""
    global _serial_manager
    
    if _serial_manager is None:
        _serial_manager = SerialManager()
        
    return _serial_manager


def initialize_serial_manager():
    """Inicializa e inicia o SerialManager global"""
    manager = get_serial_manager()
    if not manager.is_running():
        manager.start()
    return manager


def shutdown_serial_manager():
    """Para o SerialManager global"""
    global _serial_manager
    
    if _serial_manager:
        _serial_manager.stop()
        _serial_manager = None

