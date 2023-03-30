#!/usr/bin/env python
from flask import Flask
from . import config
app = Flask(__name__)
app.secret_key = config.FLASK_SESSION_KEY

from . import views