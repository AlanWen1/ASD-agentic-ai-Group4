# Cloud-only image for the Release 2 cloud bonus (RAG in the cloud).
# Locally the RAG server still runs as a non-containerised host process
# (./run_local.sh). scripts/deploy/azure-deploy.sh builds and deploys this
# image only when RAG is switched on for a manual bonus deployment.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag_server.py rag_pipeline.py ./
COPY corpus ./corpus
EXPOSE 5101
CMD ["python", "rag_server.py"]
