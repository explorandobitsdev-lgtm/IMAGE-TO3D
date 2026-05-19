# Build context = repo root (ver platform/docker-compose.yml).
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip && \
    pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu121

COPY platform/apps/worker/requirements.txt .
RUN pip install -r requirements.txt

RUN pip install git+https://github.com/VAST-AI-Research/TripoSR.git@main || echo "TripoSR install opcional"

# Módulos do repo root reutilizados pelos pipelines de heightmap/palmilha
COPY heightmap_utils.py palmilha.py image_processing.py svg_helper.py ./

# Worker em si
COPY platform/apps/worker/ ./

CMD ["python", "worker.py"]
