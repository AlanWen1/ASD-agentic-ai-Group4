# Optional cloud bonus only; do not add this service to local Docker Compose.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py tools.py ./
EXPOSE 5100
CMD ["python", "server.py"]
