#!/bin/sh
redis-server &
hypercorn -w 4 -b 0.0.0.0:8080 app:app