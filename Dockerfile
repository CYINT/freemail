FROM python:3.13-slim

WORKDIR /app

RUN adduser --disabled-password --gecos "" freemail

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt

COPY src /app/src

USER freemail

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "freemail_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
