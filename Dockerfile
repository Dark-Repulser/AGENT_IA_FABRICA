FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema (psycopg2 necesita libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código fuente
COPY agent/       ./agent/
COPY mcp_servers/ ./mcp_servers/
COPY tests/       ./tests/
COPY logger.py    ./logger.py

# Directorios de salida
RUN mkdir -p /workspace /logs

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKSPACE_PATH=/workspace

CMD ["python", "agent/agent.py"]