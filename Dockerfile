FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
# --no-access-log: request addresses carry the profile (favourites, city), so they are never written to a log
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
