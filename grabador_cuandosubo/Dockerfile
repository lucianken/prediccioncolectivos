FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código + delta.py (copia del grabador CABA, la pone stage.py) + datos de identidad y panel
COPY *.py ./
COPY LABEL_LINE_MAP.json arrival_stops.json ./
COPY referencia/datos/registry.json referencia/datos/label_line_map_overrides.json ./referencia/datos/

ENV PYTHONUNBUFFERED=1 DATA_DIR=/data

HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=180s \
  CMD python -c "import os,time,sys; f='/data/health'; sys.exit(0 if os.path.exists(f) and time.time()-os.path.getmtime(f)<180 else 1)"

CMD ["python", "grabador.py"]
