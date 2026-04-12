FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import os,time; f='/data/health'; assert os.path.exists(f) and time.time()-os.path.getmtime(f)<120"

CMD ["python", "grabador.py"]
