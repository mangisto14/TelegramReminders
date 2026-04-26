FROM python:3.11-slim

# Create a non-root user to run the bot
RUN useradd --create-home botuser

WORKDIR /app

# Install dependencies first so this layer is cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY database.py main.py ./

# Database lives on a persistent volume mounted at /data
ENV DATABASE_PATH=/data/reminders.db

# Switch to non-root user
USER botuser

CMD ["python", "main.py"]
