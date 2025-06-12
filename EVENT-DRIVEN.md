# 📋 **OVERVIEW COMPLETO - Sistema Event-Driven para Processamento de Alertas**

## 🏗️ **ARQUITETURA IMPLEMENTADA**

### **1. Estrutura Hierárquica do Sistema**

```
FastAPI Application (main.py)
├── BackgroundManager (Coordenador Principal)
│   ├── 📊 Monitores Básicos (Threads Daemon)
│   │   ├── HostMonitor (CPU, RAM, Disk, Temperature)
│   │   ├── SerialMonitor (Comunicação ESP32)
│   │   └── CameraMonitor (Conectividade das Câmeras)
│   │
│   └── 🚨 Sistema de Alertas (Event-Driven)
│       ├── EventBus (Publisher/Subscriber)
│       ├── CameraAlertProcessor (Coordenador de Alertas)
│       ├── CameraProcessor[] (Processadores Individuais)
│       └── Event Handlers (4 Essenciais)
│           ├── DatabaseHandler
│           ├── MQTTHandler
│           ├── AMQPHandler
│           └── FrigateHandler
│
└── 🎛️ API Controller (Controle Opcional)
    └── BackgroundServiceController (5 Endpoints)
```

---

## 🔄 **FLUXO COMPLETO DO SISTEMA**

### **Fase 1: Inicialização Automática (main.py)**
```python
# 1. FastAPI startup
@app.on_event("startup")
async def startup_event():
    await background_manager.startup()

# 2. BackgroundManager.startup()
# - Inicia monitores básicos (threads daemon)
# - Cria EventBus
# - Inicializa CameraAlertProcessor
# - Inicia processamento automático
```

### **Fase 2: Operação Contínua**

#### **A) Monitores Básicos (Sempre Ativos)**
- **HostMonitor**: Coleta métricas do sistema (CPU, RAM, Disk, Temperature)
- **SerialMonitor**: Monitora comunicação com ESP32
- **CameraMonitor**: Verifica conectividade das câmeras

#### **B) Sistema de Alertas (Event-Driven)**

**1. CameraAlertProcessor (Coordenador Principal)**
```python
# Loop principal de monitoramento
async def _main_processing_loop():
    while self.is_running:
        # 1. Verificar câmeras ativas no banco
        active_cameras = self._get_active_cameras()
        
        # 2. Criar/Atualizar CameraProcessor para cada câmera
        for camera in active_cameras:
            self._start_or_update_camera_processor(camera)
        
        # 3. Remover processadores de câmeras inativas
        self._cleanup_inactive_processors()
        
        await asyncio.sleep(self.check_interval)
```

**2. CameraProcessor (Processador Individual)**
```python
# Para cada câmera ativa
async def process_camera():
    while camera_active:
        # 1. Capturar frame da câmera
        frame = await self.capture_frame()
        
        # 2. Executar inferência AI (IMPLEMENTAR)
        detections = await self.run_inference(frame)
        
        # 3. Gerar alertas se necessário
        if detections:
            alert_event = self.create_alert_event(detections)
            
            # 4. Publicar no EventBus
            await self.event_bus.publish(alert_event)
```

**3. EventBus (Distribuidor de Eventos)**
```python
# Quando um alerta é publicado
async def publish(event: AlertEvent):
    # 1. Buscar todos os handlers registrados
    handlers = self._subscribers[EventType.CAMERA_ALERT_DETECTED]
    
    # 2. Executar todos os handlers em paralelo
    tasks = [handler.handle_event(event) for handler in handlers]
    await asyncio.gather(*tasks, return_exceptions=True)
```

**4. Event Handlers (Processamento Paralelo)**

- **DatabaseHandler**: Salva alerta no banco de dados
- **MQTTHandler**: Publica via MQTT (tópicos múltiplos)
- **AMQPHandler**: Envia para RabbitMQ (routing keys)
- **FrigateHandler**: Registra no Frigate (API integration)

---

## 📁 **ARQUIVOS IMPLEMENTADOS**

### **Core System**
- ✅ `background/background_manager.py` - Coordenador principal
- ✅ `background/event_system.py` - Sistema de eventos Publisher/Subscriber
- ✅ `background/camera_alert_processor.py` - Coordenador de alertas
- ✅ `background/camera_processor.py` - Processador individual de câmera

### **Monitores Básicos**
- ✅ `background/host_monitor.py` - Monitor do sistema
- ✅ `background/serial_monitor.py` - Monitor ESP32
- ✅ `background/camera_monitor.py` - Monitor de conectividade

### **Event Handlers**
- ✅ `background/handlers/database_handler.py` - Persistência no banco
- ✅ `background/handlers/mqtt_handler.py` - Publicação MQTT
- ✅ `background/handlers/amqp_handler.py` - Mensageria RabbitMQ
- ✅ `background/handlers/frigate_handler.py` - Integração Frigate

### **API Controller**
- ✅ `controllers/background_service_controller.py` - Endpoints de controle

### **Configuration**
- ✅ `requirements.txt` - Dependências atualizadas

---

## 🎛️ **ENDPOINTS DO CONTROLLER**

### **1. GET `/background/status`**
```json
{
  "status": "running",
  "is_running": true,
  "startup_completed": true,
  "basic_monitors": {
    "host_monitor": true,
    "serial_monitor": true,
    "camera_monitor": true,
    "status": "running"
  },
  "alert_processing": {
    "status": "running",
    "cameras_processing": 3,
    "total_alerts_processed": 45,
    "handlers_status": {
      "database": "active",
      "mqtt": "active",
      "amqp": "active",
      "frigate": "active"
    }
  }
}
```

### **2. POST `/background/start`**
- **Função**: Inicia processamento de alertas manualmente
- **Uso**: Após parada manual ou para debug

### **3. POST `/background/stop`**
- **Função**: Para processamento de alertas
- **Uso**: Manutenção ou debug (monitores básicos continuam)

### **4. POST `/background/restart`**
- **Função**: Reinicia sistema de alertas
- **Uso**: Aplicar novas configurações

### **5. GET `/background/health`**
- **Função**: Health check para monitoramento externo
- **Retorna**: Status de saúde do sistema

---

## ✅ **O QUE ESTÁ IMPLEMENTADO**

### **Sistema Completo**
1. ✅ **Auto-Startup**: Sistema inicia automaticamente com a aplicação
2. ✅ **Event-Driven Architecture**: Publisher/Subscriber pattern
3. ✅ **Processamento Paralelo**: Múltiplas câmeras e handlers simultâneos
4. ✅ **Tolerância a Falhas**: Falha em um componente não afeta outros
5. ✅ **API de Controle**: Endpoints para monitoramento e controle opcional
6. ✅ **Logging Estruturado**: Logs detalhados para debug e monitoramento
7. ✅ **Configuração Flexível**: Handlers opcionais baseados em configuração

### **Handlers Funcionais**
1. ✅ **DatabaseHandler**: Salva alertas com validação e estatísticas
2. ✅ **MQTTHandler**: Publica em múltiplos tópicos com retry
3. ✅ **AMQPHandler**: Envia para RabbitMQ com routing keys
4. ✅ **FrigateHandler**: Integra com API do Frigate

---

## ⚠️ **O QUE FALTA IMPLEMENTAR**

### **1. Inferência AI (CRÍTICO)**
```python
# Em camera_processor.py - Métodos que precisam ser implementados:
async def capture_frame(self) -> np.ndarray:
    """IMPLEMENTAR: Captura real do frame da câmera"""
    pass

async def run_inference(self, frame: np.ndarray) -> List[Detection]:
    """IMPLEMENTAR: Execução do modelo AI para detecção"""
    pass
```

### **2. Configuração de Handlers**
```python
# Configuração dos handlers via environment variables ou config file
MQTT_CONFIG = {
    "broker_host": "localhost",
    "broker_port": 1883,
    "username": None,
    "password": None
}

AMQP_CONFIG = {
    "amqp_url": "amqp://guest:guest@localhost:5672/"
}

FRIGATE_CONFIG = {
    "frigate_base_url": "http://localhost:5000"
}
```

### **3. Modelos de Dados**
```python
# Estruturas para detecções AI
@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: Dict[str, float]  # x, y, width, height
    metadata: Dict[str, Any]
```

---

## 🚀 **CARACTERÍSTICAS DO SISTEMA**

### **Performance**
- ⚡ **Processamento Paralelo**: Múltiplas câmeras simultâneas
- ⚡ **Handlers Assíncronos**: Todos os handlers executam em paralelo
- ⚡ **Event-Driven**: Zero overhead quando não há alertas

### **Robustez**
- 🛡️ **Tolerância a Falhas**: Isolamento entre componentes
- 🛡️ **Auto-Recovery**: Reconexão automática para MQTT/AMQP
- 🛡️ **Graceful Degradation**: Sistema continua funcionando mesmo com falhas parciais

### **Escalabilidade**
- 📈 **Horizontal**: Fácil adição de novos handlers
- 📈 **Vertical**: Suporte a múltiplas câmeras
- 📈 **Configurável**: Handlers opcionais baseados em necessidade

### **Observabilidade**
- 📊 **Logs Estruturados**: Rastreamento completo de eventos
- 📊 **Métricas**: Estatísticas de processamento e performance
- 📊 **Health Checks**: Monitoramento de saúde do sistema

---

## 🎯 **PRÓXIMOS PASSOS**

1. **Implementar Inferência AI** (Prioridade Alta)
2. **Configurar Handlers** (Prioridade Média)
3. **Testes de Integração** (Prioridade Média)
4. **Documentação de Deploy** (Prioridade Baixa)

O sistema está **arquiteturalmente completo** e **funcionalmente pronto** para receber a implementação da inferência AI! 🎉
