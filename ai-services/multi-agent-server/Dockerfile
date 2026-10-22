# Cloud-only image for the Release 2 cloud bonus (Multi-Agent in the cloud).
# Locally the Multi-Agent server still runs as a non-containerised host
# process (./run_local.sh). scripts/deploy/azure-deploy.sh builds and deploys
# this image only when Multi-Agent is switched on for a manual bonus
# deployment. Run history goes to MULTI_AGENT_DB_PATH (set to /tmp by the
# deploy script), so it is reset whenever the container restarts.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py cli.py ./
EXPOSE 5102
CMD ["python", "service.py"]
