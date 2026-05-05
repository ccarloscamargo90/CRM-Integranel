FROM python:3.11-slim

# Dependencias del sistema necesarias para psycopg, geopandas y shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (capa cacheada)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY . .

# Instalar el paquete en modo editable para que los imports src.* funcionen
RUN pip install --no-cache-dir -e .

EXPOSE 8000

# Aplica migraciones y arranca el servidor
CMD ["sh", "-c", "python -m alembic upgrade head && python scripts/seed_admin.py && uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2"]
