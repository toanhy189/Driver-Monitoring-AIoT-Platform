FROM python:3.12-slim

WORKDIR /app

COPY mqtt/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY mqtt/ ./mqtt/
COPY backend/ ./backend/

ENV PYTHONPATH=/app/backend:/app

CMD ["python", "-m", "mqtt.consumer"]