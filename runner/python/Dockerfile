FROM python:3.12-slim

RUN useradd -r -u 1001 -m runner

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py sandbox.py ./
USER runner

ENV PYTHONUNBUFFERED=1
EXPOSE 9100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9100", "--workers", "1"]
