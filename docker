# Base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all project files (except ignored in .dockerignore)
COPY . /app

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# (Optional) Show contents for debug
# RUN ls -la /app

# Start the app
CMD ["python", "homework.py"]
