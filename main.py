"""
Aplicação principal refatorada com estrutura modular
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from config.app_config import app_config
from config.database_config import create_tables
from controllers import setup_routes
from background.background_manager import background_manager
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    # Startup
    try:
        logger.info("🚀 Iniciando DIGEF-X Power Management API v2.0...")
        
        # Criar tabelas do banco de dados
        create_tables()
        logger.info("✅ Banco de dados inicializado")
        
        # Auto-startup do Background Manager
        await background_manager.startup()
        logger.info("✅ Background Manager inicializado")
        
        logger.info("🎉 DIGEF-X Power Management API v2.0 iniciada com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro durante startup da aplicação: {e}")
        # Continuar execução mesmo com erro no background
        logger.warning("⚠️ Aplicação continuará sem background processing")
    
    yield
    
    # Shutdown
    try:
        logger.info("🛑 Finalizando DIGEF-X Power Management API...")
        
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
        "status": "running",
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Verificação de saúde da API"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "uptime": "ok"
    }


# Configuração das rotas
setup_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_refactored:app",
        host="0.0.0.0",
        port=7000,
        reload=True,
        log_level="info"
    ) 