FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates/ templates/
COPY baseline.json baseline.json
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]