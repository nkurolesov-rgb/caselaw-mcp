FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY tools/ tools/
COPY entity/ entity/
# COPY events/ events/
# COPY data/ data/  # volume-mounted at runtime

EXPOSE 8006

# FastMCP uses StreamableHTTP on /mcp — no dedicated /health endpoint.
# Use TCP connection check to verify the uvicorn process is listening.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8006/mcp -o /dev/null -w '%{http_code}' | grep -qE '^[2345]' || exit 1

CMD ["python", "server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8006"]
