FROM python:3.11-slim

RUN useradd --create-home botuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY database.py main.py ./

USER botuser

CMD ["python", "main.py"]
