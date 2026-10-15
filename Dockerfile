FROM python:3.12-slim
# libfribidi lets Pillow lay out Persian, Arabic and Hindi text correctly in charts and PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends libfribidi0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY assets assets
COPY bot bot
COPY core core
COPY data data
COPY instruments instruments
ENV DB_PATH=/data/neo_bot.sqlite3 PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "-m", "bot.main"]
