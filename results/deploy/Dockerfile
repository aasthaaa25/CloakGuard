FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libnss3 libatk-bridge2.0-0 libxkbcommon0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install playwright opencv-python scapy || true
RUN playwright install --with-deps chromium || true

COPY app/ ./app/
COPY detection/ ./detection/

RUN mkdir -p data logs/forensics

EXPOSE 8443

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443"]
