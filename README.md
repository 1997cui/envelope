# A small website to generate USPS Envelopes with Trackable Barcode
## Features
1. Generate a ready-to-print envelope pdf and html
2. The envelope has a traceable barcode
3. Show status of your first class mail without certify!
## Install
### Create a `config.py` containing the following content in the root folder:
```
MAILER_ID = <Your mailer id>
SRV_TYPE=40
BARCODE_ID=0
BSG_USERNAME= <Your USPS business account username>
BSG_PASSWD= <Your USPS business account password>
```
Get a mailer ID here for free: [Guide](https://blog.ctyi.me/%E7%94%9F%E6%B4%BB/2021/06/03/USPS_IV_MTR.html)

### Modify the `Dockerfile`:
```
ENV SCRIPT_NAME=/envelope
EXPOSE 8080
```
means your service will run under:
```
http://127.0.0.1:8080/envelope/
```
### Build the docker image:
```
docker build -t envelope_image .
```
### Run it:
```
docker run -p 8083:8080 --name envelope_app -d --restart=always envelope_image
```
