FROM python:3.12-slim

WORKDIR /app

COPY student-5/frontend/. .
COPY shared/theme.css ./static/theme.css

RUN pip install --no-cache-dir flask requests

EXPOSE 3005

CMD ["python", "app.py"]
