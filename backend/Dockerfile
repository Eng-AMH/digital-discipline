FROM python:3.12-slim

# psycopg2 needs libpq at build time; kept minimal rather than pulling the full
# build-essential toolchain since psycopg2-binary (already in requirements.txt)
# ships its own compiled libpq, so only the runtime lib is needed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["daphne", "-b", "0.0.0.0", "-p", "10000", "config.asgi:application"]
