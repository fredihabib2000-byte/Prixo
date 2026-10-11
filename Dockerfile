FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No data volume any more: all data lives in Supabase (PostgreSQL).
# Secrets and DATABASE_URL are passed in at runtime (see docker-compose.yml / .env).

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
