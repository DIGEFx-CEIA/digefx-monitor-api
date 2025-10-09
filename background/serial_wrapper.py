"""
Wrapper para porta serial usando file descriptor
Solução que NÃO causa reset do ESP32
"""
import os
import select
import subprocess
import logging
import time

logger = logging.getLogger(__name__)


class SerialFileDescriptor:
    """
    Wrapper de porta serial usando file descriptor direto
    Não usa pySerial para evitar reset do ESP32
    """
    
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._fd = None
        self._is_open = False
        self._read_buffer = ""
        
    def _configure_stty(self):
        """Configura porta com stty"""
        logger.info(f"🔧 Configurando {self.port} com stty...")
        
        comandos = [
            ['stty', '-F', self.port, str(self.baudrate)],
            ['stty', '-F', self.port, 'raw'],
            ['stty', '-F', self.port, '-echo'],
            ['stty', '-F', self.port, '-hupcl'],  # CRÍTICO!
            ['stty', '-F', self.port, 'clocal'],
            ['stty', '-F', self.port, '-crtscts'],
            ['stty', '-F', self.port, '-icrnl'],
            ['stty', '-F', self.port, '-opost'],
            ['stty', '-F', self.port, '-isig'],
            ['stty', '-F', self.port, '-icanon'],
        ]
        
        for cmd in comandos:
            try:
                subprocess.run(cmd, capture_output=True, timeout=2, check=True)
            except Exception as e:
                logger.warning(f"⚠️ Erro em {cmd}: {e}")
                
        logger.info("✅ stty configurado")
        
    def open(self):
        """Abre porta serial"""
        if self._is_open:
            return
            
        try:
            # Configurar stty ANTES
            self._configure_stty()
            
            # Abrir como file descriptor (não toca em DTR/RTS!)
            self._fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            self._is_open = True
            
            logger.info(f"✅ Porta {self.port} aberta (FD: {self._fd})")
            
            # Pequena pausa para estabilização
            time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"❌ Erro ao abrir porta: {e}")
            raise
            
    def close(self):
        """Fecha porta serial"""
        if self._fd is not None:
            try:
                os.close(self._fd)
                logger.info(f"✅ Porta {self.port} fechada")
            except:
                pass
            self._fd = None
            self._is_open = False
            
    @property
    def is_open(self):
        """Retorna se porta está aberta"""
        return self._is_open
        
    @property
    def in_waiting(self):
        """Retorna número de bytes disponíveis para leitura"""
        if not self._is_open:
            return 0
            
        try:
            # Usar select para verificar se há dados
            ready, _, _ = select.select([self._fd], [], [], 0)
            if ready:
                # Tentar ler um byte para ver tamanho
                # Na verdade, não conseguimos saber exato sem ler
                # Retornar 1 se há dados
                return 1
            return 0
        except:
            return 0
            
    def read(self, size=1):
        """Lê bytes da porta"""
        if not self._is_open:
            return b''
            
        try:
            data = os.read(self._fd, size)
            return data
        except BlockingIOError:
            return b''
        except Exception as e:
            logger.error(f"❌ Erro ao ler: {e}")
            return b''
            
    def readline(self):
        """Lê uma linha da porta"""
        while '\n' not in self._read_buffer:
            # Tentar ler mais dados
            ready, _, _ = select.select([self._fd], [], [], 0.1)
            if ready:
                try:
                    data = os.read(self._fd, 1024)
                    if data:
                        self._read_buffer += data.decode('utf-8', errors='ignore')
                    else:
                        break
                except BlockingIOError:
                    break
                except Exception:
                    break
            else:
                break
                
        # Se tem newline, retornar linha
        if '\n' in self._read_buffer:
            line, self._read_buffer = self._read_buffer.split('\n', 1)
            return (line + '\n').encode('utf-8')
        
        # Se não tem, retornar vazio
        return b''
        
    def write(self, data):
        """Escreve bytes na porta"""
        if not self._is_open:
            return 0
            
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            return os.write(self._fd, data)
        except Exception as e:
            logger.error(f"❌ Erro ao escrever: {e}")
            return 0
            
    def flush(self):
        """Flush (não faz nada em file descriptor)"""
        pass
        
    def reset_input_buffer(self):
        """Limpa buffer de entrada"""
        self._read_buffer = ""
        if self._is_open:
            try:
                # Ler e descartar tudo que há
                while True:
                    ready, _, _ = select.select([self._fd], [], [], 0)
                    if not ready:
                        break
                    data = os.read(self._fd, 4096)
                    if not data:
                        break
            except:
                pass
                
    def reset_output_buffer(self):
        """Limpa buffer de saída (não aplicável)"""
        pass
        
    # Propriedades dummy para compatibilidade
    @property
    def dtr(self):
        return False
        
    @dtr.setter
    def dtr(self, value):
        pass  # Não implementado (proposital)
        
    @property
    def rts(self):
        return False
        
    @rts.setter  
    def rts(self, value):
        pass  # Não implementado (proposital)







