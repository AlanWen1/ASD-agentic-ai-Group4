FROM python:3.11-slim

WORKDIR /app

COPY expense-category-tracker/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY expense-category-tracker/frontend/. .
COPY shared/theme.css ./static/theme.css

EXPOSE 3002

CMD ["python", "app.py"]
