FROM python:3.11

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "src/main.py"]