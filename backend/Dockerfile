FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN pip install --no-cache-dir ./backend \
    && addgroup --system aegis \
    && adduser --system --ingroup aegis aegis
COPY frontend frontend

WORKDIR /workspace/backend

EXPOSE 8000
USER aegis

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
