FROM python:3.10-buster

# handle static files
ENV STATIC_URL /static
ENV STATIC_PATH /data/web/static

# set working directory and import /data/web/*
COPY ./data/web /data/web
WORKDIR /data/web

# make /data/web* available to be imported
ENV PYTHONPATH=/data/web
ENV FLASK_APP /data/web/app.py
ENV FLASK_RUN_HOST 0.0.0.0

# install requirements & set timezone
COPY requirements.txt .
RUN python -m pip install -r requirements.txt \
&& ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# copy everything
COPY . .

# run flask
CMD ["flask", "run"]
