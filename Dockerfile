FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy server script and public web files
COPY server.py /app/server.py
COPY public/ /app/public/

# Create data folder for database volume mounts
RUN mkdir -p /app/data

# Expose the API/Web server port
EXPOSE 8000

# Run Python in unbuffered mode to flush console prints to container logs immediately
CMD ["python", "-u", "server.py"]
