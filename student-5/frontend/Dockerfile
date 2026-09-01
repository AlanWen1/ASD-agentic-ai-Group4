FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask requests

EXPOSE 3005

CMD ["python", "app.py"]