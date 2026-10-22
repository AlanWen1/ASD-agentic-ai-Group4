# Cloud-only image for the Release 2 cloud bonus (MCP in the cloud).
# Locally the MCP server still runs as a non-containerised host process
# (./run_local.sh), as the Release 1/2 briefs require. scripts/deploy/
# azure-deploy.sh builds and deploys this image only when MCP is switched on
# for a manual bonus deployment.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py tools.py ./
EXPOSE 5100
CMD ["python", "server.py"]
