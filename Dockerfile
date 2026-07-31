FROM python:3.12-slim

WORKDIR /srv/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY ai_layer ai_layer

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Render/Railway/Fly inject $PORT; default to 8000 for plain `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
