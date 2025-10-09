FROM python:3.10

# Instala dependências do sistema para serial, banco, build, execução no host e bibliotecas gráficas
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    python3-dev \
    gcc \
    libudev-dev \
    util-linux \
    procps \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia dependências e instala
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN pip uninstall -y opencv-python
RUN pip uninstall -y opencv-contrib-python
RUN pip install opencv-contrib-python-headless==4.11.0.86

# Copia o restante da aplicação
COPY . .

# Expõe a porta da API
EXPOSE 7000

# Comando padrão
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
