FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 CHULLO_PUBLIC=1 CHULLO_ENABLE_DETECTION=0
WORKDIR /app
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements-detection.txt .
RUN pip install --no-cache-dir -r requirements-detection.txt
COPY backend backend
COPY scripts scripts
COPY servidor.py .
COPY web web
COPY data/imagery/chullo data/imagery/chullo
COPY models/chullo_local_v1 models/chullo_local_v1
RUN python scripts/ensure_weights.py
EXPOSE 8080
CMD ["python", "servidor.py"]
