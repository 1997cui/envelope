import json
from . import config
import aioredis
import datetime
import time
import sys
import xmltodict
import html
import httpx
import asyncio
from urllib.parse import urljoin

USPS_API_URL="https://services.usps.com"
USPS_SERVICE_API_BASE="https://iv.usps.com/ivws_api/informedvisapi/"
USPS_ADDRESS_API_URL = 'https://secure.shippingapis.com/ShippingAPI.dll'

headers = {'Content-type': 'application/json'}

redis_client = aioredis.Redis(host=config.REDIS_HOST, port=6379, db=0)
httpx_client = httpx.AsyncClient(timeout=15)

async def generate_token_usps(username: str,
                   passwd: str):
    data = {
    "username": username, 
    "password": passwd, 
    "grant_type": "authorization", 
    "response_type": "token", 
    "scope": "user.info.ereg,iv1.apis", 
    "client_id": "687b8a36-db61-42f7-83f7-11c79bf7785e"}
    response = await httpx_client.post(urljoin(USPS_API_URL, "oauth/authenticate"), data=json.dumps(data), headers=headers)
    return response.json()

async def refresh_token_usps(refresh_token: str):
    data = {
        "refresh_token": refresh_token,
        "grant_type": "authorization",
        "response_type": "token",
        "scope": "user.info.ereg,iv1.apis"
    }
    response = await httpx_client.post(urljoin(USPS_API_URL, "oauth/token"), data=json.dumps(data), headers=headers)
    return response.json()

async def token_maintain():
    access_token = await redis_client.get("usps_access_token")
    next_refresh_time = await redis_client.get("usps_token_nextrefresh")
    refresh_token = await redis_client.get("usps_refresh_token")
    now = datetime.datetime.now()
    if next_refresh_time is not None:
        next_refresh_time = datetime.datetime.fromtimestamp(float(next_refresh_time.decode('utf-8')))
    if next_refresh_time is None or now > next_refresh_time:
        resp = await generate_token_usps(config.BSG_USERNAME, config.BSG_PASSWD)
        token_type = resp['token_type']
        access_token = resp['access_token']
        refresh_token = resp['refresh_token']
        expires_in = int(resp['expires_in'])
        refresh_token = resp['refresh_token']
        await redis_client.set("usps_access_token", access_token)
        await redis_client.set("usps_token_nextrefresh", time.time() + expires_in/2.0)
        await redis_client.set("usps_refresh_token", refresh_token)
        await redis_client.set("usps_token_type", token_type)
    else:
        refresh_token = refresh_token.decode('utf-8')
        resp = await refresh_token_usps(refresh_token)
        expires_in = int(resp['expires_in'])
        await redis_client.set("usps_token_nextrefresh", time.time() + expires_in/2.0)

async def get_authorization_header():
    next_refresh_time = await redis_client.get("usps_token_nextrefresh")
    if next_refresh_time is not None:
        next_refresh_time = datetime.datetime.fromtimestamp(float(next_refresh_time.decode('utf-8')))
    now = datetime.datetime.now()
    if next_refresh_time is None or now > next_refresh_time:
        await token_maintain()
    access_token = (await redis_client.get("usps_access_token")).decode('utf-8')
    token_type =  (await redis_client.get("usps_token_type")).decode('utf-8')
    headers_local = dict()
    headers_local["Authorization"] = token_type + " " + access_token
    return headers_local

async def get_piece_tracking(imb: str):
    url = urljoin(USPS_SERVICE_API_BASE, "api/mt/get/piece/imb/" + imb)
    response = await httpx_client.get(url, headers=await get_authorization_header())
    return response.json()

async def get_USPS_standardized_address(address):
    req = ""
    if 'firmname' in address:
        req += f"<FirmName>{address['firmname']}</FirmName>"
    req += str(f"""
        <Address1>{address['address1']}</Address1>
        <Address2>{address['address2']}</Address2>
        <City>{address['city']}</City>
        <State>{address['state']}</State>
        <Zip5>{address['zip5']}</Zip5>
    """)
    if 'zip4' in address:
        req += f"<Zip4>{address['zip4']}</Zip4>"
    else:
        req += "<Zip4/>"
    
    address_xml = f"""
    <Address ID="0">{req}</Address>
    """

    request_xml = f"""
    <AddressValidateRequest USERID="{config.USPS_WEBAPI_USERNAME}">
        <Revision>1</Revision>
        {address_xml}
    </AddressValidateRequest>
    """

    response = await httpx_client.get(USPS_ADDRESS_API_URL, params={'API': 'Verify', 'XML': request_xml})
    response_dict = xmltodict.parse(response.content)

    if 'Error' in response_dict:
        return {'error': html.unescape(response_dict['Error']['Description'])}

    if 'Error' in response_dict['AddressValidateResponse']['Address']:
        return {'error': html.unescape(response_dict['AddressValidateResponse']['Address']['Error']['Description'])}

    if 'Address1' not in response_dict['AddressValidateResponse']['Address']:
        response_dict['AddressValidateResponse']['Address']['Address1'] = ''
    if 'FirmName' not in response_dict['AddressValidateResponse']['Address']:
        response_dict['AddressValidateResponse']['Address']['FirmName'] = ''
    standardized_address = {
        'firmname': response_dict['AddressValidateResponse']['Address']['FirmName'],
        'address1': response_dict['AddressValidateResponse']['Address']['Address1'],
        'address2': response_dict['AddressValidateResponse']['Address']['Address2'],
        'city': response_dict['AddressValidateResponse']['Address']['City'],
        'state': response_dict['AddressValidateResponse']['Address']['State'],
        'zip5': response_dict['AddressValidateResponse']['Address']['Zip5'],
        'zip4': response_dict['AddressValidateResponse']['Address']['Zip4'],
        'dp': response_dict['AddressValidateResponse']['Address']['DeliveryPoint'],
    }

    return standardized_address


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print(loop.run_until_complete(get_piece_tracking(sys.argv[1])))
