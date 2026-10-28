FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py *.html ./
COPY static ./static
COPY assetlinks.json ./
RUN mkdir -p downloads
ENV APP_ENV=production SEED_SAMPLE=0
# DATABASE_URL-ը տրվում է գործարկելիս (docker compose / հոսթինգ)
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
