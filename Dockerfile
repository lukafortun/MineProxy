FROM python:3.11-slim

WORKDIR /app

COPY . .


RUN pip install --no-cache-dir -r requirements.txt

# Init DB
# RUN mkdir -p db && sqlite3 db/proxy.db < db/schema.sql

EXPOSE 25565
EXPOSE 8000

CMD ["sh", "-c", "python3 -u proxy.py & uvicorn api:app --host 0.0.0.0 --port 8000"]
