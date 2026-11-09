FROM python:3.11-slim
WORKDIR /code
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY notification_service ./notification_service
COPY audit_service ./audit_service
COPY soap_service ./soap_service
COPY event_publisher.py ./event_publisher.py
EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
