FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8090

CMD ["sh", "-c", "python -m ai_news_feed.subscriptions --serve --host 0.0.0.0 --port ${PORT:-8090} --db-path ${SUBSCRIPTION_DB_PATH:-/tmp/subscribers.db}"]
