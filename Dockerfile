FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for your packages
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf2.0-dev \
    libffi-dev \
    shared-mime-info \
    libgl1-mesa-dev \
    libgles2-mesa-dev \
    libegl1-mesa-dev \
    libdrm-dev \
    libxcb1-dev \
    ffmpeg \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libavfilter-dev \
    libavdevice-dev \
    libswscale-dev \
    libswresample-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NIXPACKS_PATH=/opt/venv/bin:$NIXPACKS_PATH

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install packages
RUN python -m venv --copies /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Expose port (adjust if needed)
EXPOSE 8000


# Activate virtual environment and run the application
CMD ["/opt/venv/bin/python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
