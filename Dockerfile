# Use an official Python runtime as a parent image, based on Ubuntu to easily install clang/llvm
FROM python:3.10-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (LLVM, Clang, and build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    clang \
    llvm \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Ensure upload and output directories exist
RUN mkdir -p backend/uploads backend/outputs

# Expose the port the app runs on (Render provides PORT env var, we'll bind to it or fallback to 5000)
EXPOSE 5000

# Run gunicorn targeting the Flask app
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 backend.app:app
