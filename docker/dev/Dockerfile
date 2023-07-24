FROM python:3.11.4-slim-bullseye

RUN apt-get update && apt-get install -y postgresql-client curl build-essential

ENV ASGI_APPLICATION_PATH $ASGI_APPLICATION_PATH
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
#RUN python -m spacy download mk_core_news_md

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD hypercorn ${ASGI_APPLICATION_PATH} --bind 0.0.0.0:8000 --reload
