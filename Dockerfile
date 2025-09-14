FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && \
    apt-get install -y ipmitool ssh-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN useradd --create-home appuser
USER appuser
COPY --chown=appuser:appuser . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "fan_controller.py"]
