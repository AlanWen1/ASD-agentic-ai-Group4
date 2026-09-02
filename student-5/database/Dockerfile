FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir flask

EXPOSE 6005

CMD ["python", "app.py"]