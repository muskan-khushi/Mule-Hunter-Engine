FROM python:3.10-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Workdir inside container
WORKDIR /app

# System deps (safe for ML libs)
RUN apt-get update && apt-get install -y \
  gcc \
  libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy FastAPI app
COPY app ./app

# Copy other folders ONLY if needed at runtime
COPY visualization ./visualization
COPY scripts ./scripts



EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
