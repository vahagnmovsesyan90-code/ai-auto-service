FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py *.html ./
ENV APP_ENV=production AUTOSERVICE_DB=/data/autoservice.db SEED_SAMPLE=0
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
