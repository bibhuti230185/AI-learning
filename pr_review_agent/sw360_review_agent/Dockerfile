FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# Copy source
COPY src/ src/
COPY config.example.yaml config.yaml

EXPOSE 8090

CMD ["sw360-review", "server"]
