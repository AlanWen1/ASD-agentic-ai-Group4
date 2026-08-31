FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATABASE_PATH=/app/database/budget_manager.db
EXPOSE 5001
CMD ["python", "app.py"]
