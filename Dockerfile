FROM python:3.11-slim

# Instala dependências do sistema para serial, banco e build
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    python3-dev \
    gcc \
    libudev-dev \
    && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

# Expõe a porta da API
EXPOSE 7000

# Comando padrão
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
