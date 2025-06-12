"""
Aplicação principal refatorada com estrutura modular
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from config.app_config import app_config
from config.database_config import create_tables
from controllers import setup_routes
from background.background_manager import background_manager
import logging

logger = logging.getLogger(__name__)

# Flag para controlar se o background está pronto
_background_ready = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    global _background_ready
    
    # Startup - Inicializar background ANTES da aplicação ficar disponível
    try:
        logger.info("🚀 Iniciando DIGEF-X Power Management API v2.0...")
        
        # 1. Criar tabelas do banco de dados
        create_tables()
        logger.info("✅ Banco de dados inicializado")
        
        # 2. Inicializar Background Manager (CRÍTICO - deve completar antes da API)
        logger.info("⏳ Inicializando sistema de background...")
        await background_manager.startup()
        logger.info("✅ Background Manager inicializado")
        
        # 3. Marcar background como pronto (API disponível)
        _background_ready = True
        logger.info("🎉 DIGEF-X Power Management API v2.0 PRONTA para receber requisições!")
        logger.info("🔄 Processamento de alertas iniciando em background...")
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO durante startup: {e}")
        # Se o background falhar, a aplicação não deve ficar disponível
        _background_ready = False
        logger.error("🚫 API NÃO ESTÁ PRONTA - Background falhou na inicialização")
        raise  # Isso fará o uvicorn falhar e não aceitar conexões
    
    yield  # Aplicação fica disponível APENAS se chegou até aqui
    
    # Shutdown
    try:
        logger.info("🛑 Finalizando DIGEF-X Power Management API...")
        _background_ready = False
        
        # Finalizar Background Manager
        await background_manager.shutdown()
        logger.info("✅ Background Manager finalizado")
        
        logger.info("👋 API finalizada com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro durante shutdown: {e}")

# Inicialização da aplicação
app = FastAPI(
    title="DIGEF-X Power Management API",
    description="API para monitoramento de energia e gerenciamento de dispositivos",
    version="2.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
    lifespan=lifespan
)

# Middleware para verificar se background está pronto
@app.middleware("http")
async def check_background_ready(request, call_next):
    """Middleware que bloqueia apenas endpoints críticos se o background não estiver pronto"""
    # Endpoints sempre disponíveis
    always_available = ["/", "/health", "/docs", "/openapi.json", "/redoc"]
    
    # Endpoints de background sempre disponíveis (para monitoramento)
    background_endpoints = ["/background/status", "/background/health"]
    
    # Permitir endpoints básicos e de monitoramento
    if any(request.url.path.startswith(path) for path in always_available + background_endpoints):
        return await call_next(request)
    
    # Para outros endpoints, verificar se background está pronto
    if not _background_ready:
        raise HTTPException(
            status_code=503, 
            detail="Sistema ainda inicializando. Aguarde alguns segundos e tente novamente."
        )
    
    return await call_next(request)

# Configuração de segurança para Swagger
bearer_scheme = HTTPBearer()

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_openapi():
    """Configuração customizada do OpenAPI para incluir autenticação JWT"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="DIGEF-X Power Management API",
        version="2.0.0",
        description="API para monitoramento de energia e gerenciamento de dispositivos",
        routes=app.routes,
    )
    
    # Limpar security schemes existentes e adicionar apenas o nosso
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Insira o token JWT obtido no endpoint /api/v1/login"
        }
    }
    
    # Atualizar todos os paths protegidos para usar BearerAuth
    for path, path_item in openapi_schema["paths"].items():
        for method, operation in path_item.items():
            if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"] and "security" in operation:
                # Substituir qualquer security scheme por BearerAuth
                operation["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
async def root():
    """Endpoint raiz da API"""
    return {
        "message": "DIGEF-X Power Management API v2.0",
        "status": "ready" if _background_ready else "initializing",
        "background_ready": _background_ready,
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Verificação de saúde da API"""
    status = "healthy" if _background_ready else "initializing"
    
    health_data = {
        "status": status,
        "version": "2.0.0",
        "background_ready": _background_ready,
        "uptime": "ok"
    }
    
    # Se background estiver pronto, incluir detalhes
    if _background_ready and background_manager.is_ready:
        try:
            bg_status = background_manager.get_status()
            health_data["background_status"] = bg_status
        except Exception as e:
            health_data["background_error"] = str(e)
    
    return health_data


# Configuração das rotas
setup_routes(app)
