# Runtime image for the MOFA-Guided Oncology Research Copilot API.
#
# This image never bakes in raw METABRIC data or the 33 GB GCTX file -- only
# the small, versioned artifact/table directories under outputs/ (mounted as
# a volume by docker-compose.yml) are read at runtime.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY packages/pipeline_core /app/packages/pipeline_core
RUN pip install --no-cache-dir -e /app/packages/pipeline_core

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

COPY apps/api/app /app/apps/api/app

ENV PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app/apps/api
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
