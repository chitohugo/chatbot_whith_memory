FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar una versión fija de uv para respetar uv.lock durante el build.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

# Copiar archivos de configuración de dependencias
COPY pyproject.toml uv.lock ./
COPY README* ./

# Crear el entorno reproducible desde el lockfile.
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Copiar el resto del código
COPY . .

# Dar permisos de ejecución al entrypoint
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"]