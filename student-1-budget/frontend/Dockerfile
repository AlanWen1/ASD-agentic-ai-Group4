FROM python:3.11-slim
WORKDIR /app
COPY student-1-budget/frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY student-1-budget/frontend/. .
COPY shared/theme.css ./static/theme.css
EXPOSE 5000
CMD ["python", "server.py"]
