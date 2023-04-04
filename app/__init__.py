#!/usr/bin/env python
from quart import Quart
from . import config
app = Quart(__name__)
app.secret_key = config.FLASK_SESSION_KEY

from . import views