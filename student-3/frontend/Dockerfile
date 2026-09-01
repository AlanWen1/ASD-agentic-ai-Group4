FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home appuser
COPY --chown=appuser:appuser app.py ./
COPY --chown=appuser:appuser templates ./templates
COPY --chown=appuser:appuser static ./static

USER appuser
EXPOSE 3003
CMD ["python", "app.py"]
