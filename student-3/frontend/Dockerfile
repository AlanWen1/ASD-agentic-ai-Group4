FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY student-3/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home appuser
COPY --chown=appuser:appuser student-3/frontend/app.py ./
COPY --chown=appuser:appuser student-3/frontend/templates ./templates
COPY --chown=appuser:appuser student-3/frontend/static ./static
COPY --chown=appuser:appuser shared/theme.css ./static/theme.css

USER appuser
EXPOSE 3003
CMD ["python", "app.py"]
