# base image
FROM python:3.9-bullseye

# set working directory
WORKDIR /app

# copy requirements.txt
COPY requirements.txt .

# install dependencies
RUN apt-get update 
RUN apt-get install -y apt-utils redis-server
RUN apt-get install -y wget fonts-liberation fonts-wqy-zenhei fonts-arphic-uming

RUN pip install --no-cache-dir -r requirements.txt
RUN wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.bullseye_amd64.deb
RUN apt-get install -y ./wkhtmltox_0.12.6.1-2.bullseye_amd64.deb

# copy source code
COPY . .

# set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV SCRIPT_NAME=/envelope

EXPOSE 8080

CMD ["./entrypoint.sh"]