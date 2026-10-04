FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de configuración de dependencias
COPY pyproject.toml .
# Copiar README o archivos necesarios si pyproject.toml los requiere para la compilación
COPY README* ./

# Instalar las dependencias directamente desde pyproject.toml
RUN pip install --no-cache-dir .

# Copiar el resto del código
COPY . .

# Dar permisos de ejecución al entrypoint
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"]