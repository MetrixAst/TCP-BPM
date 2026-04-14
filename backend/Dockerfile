FROM python:3.11-slim

RUN mkdir -p /home/app

ENV HOME=/home/app
ENV APP_HOME=/home/app/web

RUN mkdir $APP_HOME
RUN mkdir $APP_HOME/static
RUN mkdir $APP_HOME/media

# рабочая директория внутри проекта
WORKDIR $APP_HOME

# переменные окружения для python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем зависимости для Postgre
RUN apt-get update
    # && apt-get install postgresql-dev gcc python3-dev libressl-dev musl-dev build-base jpeg-dev zlib-dev libffi-dev openssl
RUN apt-get -y install python3-dev libpq-dev postgresql-contrib gcc netcat-traditional python3-cffi


# устанавливаем зависимости
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# копирование entrypoint-prod.sh
COPY ./entrypoint.sh $APP_HOME

# копируем содержимое текущей папки в контейнер
COPY . $APP_HOME