# Envelope
---
A lightweight web service to generate USPS first class mail envelope with a traceable barcode.
## Features
1. Generate a ready-to-print envelope pdf and html
2. Support both #10 Envelope and 4in*2in label
3. The envelope has a traceable barcode
4. Show status of your first class mail without certify!
## Install
### Generate config
 - Move `app/config.py.example` to `app/config.py`
 - config your USPS Web Tools API username, Business Gateway username and Password [Guide](https://blog.ctyi.me/%E7%94%9F%E6%B4%BB/2021/06/03/USPS_IV_MTR.html)

 - config a Flask session key
 - Config your redis server address
### Docker
 - Modify the docker file to meet your need
   - `CMD ["gunicorn", "app:app", "--workers", "4", "--worker-class", "app.ConfigurableWorker", "--bind", "0.0.0.0:8080", "--forwarded-allow-ips",""]`
     - Define the path and the port
 - `docker-compose up -d`
### Enjoy
 - Open `http://localhost:8080/envelope/` in your browser