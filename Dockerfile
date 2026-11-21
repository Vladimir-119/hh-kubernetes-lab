FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py source_tools.py ./
COPY data/it_vacancies.jsonl ./data/it_vacancies.jsonl

ENTRYPOINT ["python", "worker.py"]
