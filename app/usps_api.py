import requests
import json
from . import config
import redis
import datetime
import time
import copy
import sys

USPS_API_URL="https://services.usps.com"
USPS_SERVICE_API_BASE="https://iv.usps.com/ivws_api/informedvisapi"

headers = {'Content-type': 'application/json'}

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def generate_token_usps(username: str,
                   passwd: str):
    data = {
    "username": username, 
    "password": passwd, 
    "grant_type": "authorization", 
    "response_type": "token", 
    "scope": "user.info.ereg,iv1.apis", 
    "client_id": "687b8a36-db61-42f7-83f7-11c79bf7785e"}
    response = requests.post(USPS_API_URL + "/oauth/authenticate", data=json.dumps(data), headers=headers)
    return response.json()

def refresh_token_usps(refresh_token: str):
    data = {
        "refresh_token": refresh_token,
        "grant_type": "authorization",
        "response_type": "token",
        "scope": "user.info.ereg,iv1.apis"
    }
    response = requests.post(USPS_API_URL + "/oauth/token", data=json.dumps(data), headers=headers)
    return response.json()

def token_maintain():
    access_token = redis_client.get("usps_access_token")
    next_refresh_time = redis_client.get("usps_token_nextrefresh")
    refresh_token = redis_client.get("usps_refresh_token")
    now = datetime.datetime.now()
    if next_refresh_time is not None:
        next_refresh_time = datetime.datetime.fromtimestamp(float(next_refresh_time.decode('utf-8')))
    if next_refresh_time is None or now > next_refresh_time:
        resp = generate_token_usps(config.BSG_USERNAME, config.BSG_PASSWD)
        token_type = resp['token_type']
        access_token = resp['access_token']
        refresh_token = resp['refresh_token']
        expires_in = int(resp['expires_in'])
        refresh_token = resp['refresh_token']
        redis_client.set("usps_access_token", access_token)
        redis_client.set("usps_token_nextrefresh", time.time() + expires_in/2.0)
        redis_client.set("usps_refresh_token", refresh_token)
        redis_client.set("usps_token_type", token_type)
    else:
        refresh_token = refresh_token.decode('utf-8')
        resp = refresh_token_usps(refresh_token)
        expires_in = int(resp['expires_in'])
        redis_client.set("usps_token_nextrefresh", time.time() + expires_in/2.0)

def get_authorization_header():
    token_maintain()
    access_token = redis_client.get("usps_access_token").decode('utf-8')
    token_type =  redis_client.get("usps_token_type").decode('utf-8')
    headers_local = dict()
    headers_local["Authorization"] = token_type + " " + access_token
    return headers_local

def get_piece_tracking(imb: str):
    url = USPS_SERVICE_API_BASE + "/api/mt/get/piece/imb/" + imb
    response = requests.get(url, headers=get_authorization_header())
    return response.json()


if __name__ == "__main__":
    print(get_piece_tracking(sys.argv[1]))
