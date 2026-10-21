# Optional cloud bonus only; local execution remains a host process.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag_server.py rag_pipeline.py ./
COPY corpus corpus
EXPOSE 5101
CMD ["python", "rag_server.py"]
