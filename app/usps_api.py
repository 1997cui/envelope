from urllib.parse import urljoin
import asyncio
import datetime
import time
import sys
import html
import xmltodict
from redis import asyncio as aioredis
import httpx

from . import config
from . import app


USPS_API_URL = "https://services.usps.com"
USPS_SERVICE_API_BASE = "https://iv.usps.com/ivws_api/informedvisapi/"
USPS_ADDRESS_API_URL = 'https://secure.shippingapis.com/ShippingAPI.dll'
USPS_NEW_API_URL_BASE = "https://apis.usps.com/"

headers = {'Content-type': 'application/json'}

class AuthorizationTokenError(RuntimeError):
    """Exception raised when the authorization token cannot be retrieved from Redis."""
    pass

redis_client = aioredis.Redis(host=config.REDIS_HOST, port=6379, db=0)
httpx_client = httpx.AsyncClient(timeout=15)

async def generate_usps_new_api_token(customer_id: str, customer_secret: str):
    data = {
        "client_id": customer_id,
        "client_secret": customer_secret,
        "grant_type": "client_credentials"
    }
    headers_local = {
        'Content-Type': 'application/json'
    }
    try:
        full_url = urljoin(USPS_NEW_API_URL_BASE, "/oauth2/v3/token")
        httpx_client = httpx.AsyncClient(timeout=15)
        response = await httpx_client.post(full_url, headers=headers_local, json=data)
        response.raise_for_status()
    except httpx.HTTPError as err:
        return {"error": "HTTPError", "error_description": str(err)}
    try:
        resp_json = response.json()
    except ValueError:
        return {"error": "ValueError", "error_description": "Invalid JSON response"}
    return resp_json

async def new_api_token_maintain():
    access_token = await redis_client.get("usps_new_api_access_token")
    token_expiry_time = await redis_client.get("usps_new_api_access_token_expiry")
    now = time.time()
    if token_expiry_time is not None:
        token_expiry_time = float(token_expiry_time.decode('utf-8'))
    if token_expiry_time is None or now >= token_expiry_time:
        # Token is expired or absent; obtain a new token
        app.logger.info("Trying to get USPS Oauth token from new API")
        resp = await generate_usps_new_api_token(config.USPS_NEWAPI_CUSTOMER_ID, config.USPS_NEWAPI_CUSTOMER_SECRET)
        if "error" in resp:
            app.logger.error(f"Failed to get new token, {resp}")
            return
        access_token = resp.get('access_token')
        if access_token is None:
            return
        token_type = resp.get('token_type', 'Bearer')
        expires_in = int(resp.get('expires_in', -1))  
        token_expiry_time = now + expires_in / 2.0
        # Store the token and expiry time in Redis
        await redis_client.set("usps_new_api_access_token", access_token)
        await redis_client.set("usps_new_api_token_type", token_type)
        await redis_client.set("usps_new_api_access_token_expiry", token_expiry_time)


async def generate_iv_token_usps(username: str,
                              passwd: str):
    data = {
        "username": username,
        "password": passwd,
        "grant_type": "authorization",
        "response_type": "token",
        "scope": "user.info.ereg,iv1.apis",
        "client_id": "687b8a36-db61-42f7-83f7-11c79bf7785e"}
    try:
        response = await httpx_client.post(urljoin(USPS_API_URL, "oauth/authenticate"), json=data, headers=headers)
    except httpx.HTTPError as err:
        return {"error": "HTTPError", "error_description": str(err)}
    try:
        response = response.json()
    except ValueError:
        return {"error": "ValueError", "error_description": "Invalid JSON"}
    return response


async def refresh_iv_token_usps(refresh_token: str):
    data = {
        "refresh_token": refresh_token,
        "grant_type": "authorization",
        "response_type": "token",
        "scope": "user.info.ereg,iv1.apis"
    }
    try:
        response = await httpx_client.post(urljoin(USPS_API_URL, "oauth/token"), json=data, headers=headers)
    except httpx.HTTPError as err:
        return {"error": "HTTPError", "error_description": str(err)}
    return response.json()


async def iv_token_maintain():
    access_token = await redis_client.get("usps_access_token")
    next_refresh_time = await redis_client.get("usps_token_nextrefresh")
    refresh_token = await redis_client.get("usps_refresh_token")
    now = datetime.datetime.now()
    if next_refresh_time is not None:
        next_refresh_time = datetime.datetime.fromtimestamp(
            float(next_refresh_time.decode('utf-8')))
    if next_refresh_time is None or now > next_refresh_time:
        resp = await generate_iv_token_usps(config.BSG_USERNAME, config.BSG_PASSWD)
        if "error" in resp:
            return
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
        resp = await refresh_iv_token_usps(refresh_token)
        if "error" in resp:
            return
        token_type = resp['token_type']
        access_token = resp['access_token']
        expires_in = int(resp['expires_in'])
        await redis_client.set("usps_access_token", access_token)
        await redis_client.set("usps_token_type", token_type)
        await redis_client.set("usps_token_nextrefresh", time.time() + expires_in/2.0)


async def get_iv_authorization_header():
    next_refresh_time = await redis_client.get("usps_token_nextrefresh")
    if next_refresh_time is not None:
        next_refresh_time = datetime.datetime.fromtimestamp(
            float(next_refresh_time.decode('utf-8')))
    now = datetime.datetime.now()
    if next_refresh_time is None or now > next_refresh_time:
        await iv_token_maintain()
    access_token = (await redis_client.get("usps_access_token")).decode('utf-8')
    token_type = (await redis_client.get("usps_token_type")).decode('utf-8')
    headers_local = dict()
    headers_local["Authorization"] = token_type + " " + access_token
    return headers_local

async def get_new_api_authorization_header():
    try:
        token_expiry_time = await redis_client.get("usps_new_api_access_token_expiry")
        if token_expiry_time is not None:
            token_expiry_time = float(token_expiry_time.decode('utf-8'))
        now = time.time()
        if token_expiry_time is None or now >= token_expiry_time:
            await new_api_token_maintain()
        access_token = await redis_client.get("usps_new_api_access_token")
        token_type = await redis_client.get("usps_new_api_token_type")

        if not access_token or not token_type:
            app.logger.error("Unable to obtain USPS Address API access token")
            raise AuthorizationTokenError("Unable to obtain USPS Address API access token")

        headers_local = {
            "Authorization": f"{token_type.decode('utf-8')} {access_token.decode('utf-8')}"
        }
        return headers_local
    except Exception as e:
        app.logger.exception("Exception occurred in get_address_authorization_header")
        raise


async def get_piece_tracking(imb: str):
    url = urljoin(USPS_SERVICE_API_BASE, "api/mt/get/piece/imb/" + imb)
    try:
        response = await httpx_client.get(url, headers=await get_iv_authorization_header())
    except httpx.HTTPError as err:
        return {"error": "HTTPError", "error_description": str(err)}
    return response.json()


async def get_USPS_standardized_address(address):
    req = ""
    if 'firmname' in address:
        req += f"<FirmName>{address['firmname']}</FirmName>"
    req += str(f"""
        <Address1>{address['address2']}</Address1>
        <Address2>{address['street_address']}</Address2>
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
    try:
        response = await httpx_client.get(USPS_ADDRESS_API_URL, params={'API': 'Verify', 'XML': request_xml})
    except httpx.HTTPError as err:
        return {"error": "HTTPError", "error_description": str(err)}
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
        'address2': response_dict['AddressValidateResponse']['Address']['Address1'],
        'street_address': response_dict['AddressValidateResponse']['Address']['Address2'],
        'city': response_dict['AddressValidateResponse']['Address']['City'],
        'state': response_dict['AddressValidateResponse']['Address']['State'],
        'zip5': response_dict['AddressValidateResponse']['Address']['Zip5'],
        'zip4': response_dict['AddressValidateResponse']['Address']['Zip4'],
        'dp': response_dict['AddressValidateResponse']['Address'].get('DeliveryPoint', ''),
    }

    return standardized_address


async def get_USPS_standardized_address_new(address):
    params = {
        'firm': address.get("firmname", ''),
        'streetAddress': address.get('street_address', ''),
        'secondaryAddress': address.get('address2', ''),
        'city': address.get('city', ''),
        'state': address.get('state', ''),
        'ZIPCode': address.get('zip5', ''),
        'ZIPPlus4': address.get('zip4', ''),
    }

    # Clean up empty parameters
    params = {k: v for k, v in params.items() if v}

    try:
        headers = await get_new_api_authorization_header()
        headers['accept'] = 'application/json'

        response = await httpx_client.get(
            urljoin(USPS_NEW_API_URL_BASE, '/addresses/v3/address'),
            headers=headers,
            params=params
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            # Unauthorized; attempt to refresh the token and retry once
            app.logger.warning("Unauthorized response, refreshing access token and retrying")
            await new_api_token_maintain()
            headers = await get_new_api_authorization_header()
            response = await httpx_client.get(
                urljoin(USPS_NEW_API_URL_BASE, '/addresses/v3/address'),
                headers=headers,
                params=params
            )
            response.raise_for_status()
        else:
            app.logger.error(f"HTTP error occurred: {exc}")
            return {"error": "HTTPError", "error_description": str(exc)}
    except Exception as exc:
        app.logger.exception("Exception occurred in get_USPS_standardized_address_new")
        return {"error": "Exception", "error_description": str(exc)}

    try:
        response_data = response.json()
    except ValueError:
        app.logger.error("ValueError: Invalid JSON response from USPS Address API")
        return {"error": "ValueError", "error_description": "Invalid JSON response"}

    if 'errors' in response_data:
        app.logger.error(f"Error response from USPS Address API: {response_data['errors']}")
        return {'error': response_data['errors']}

    # Extract the standardized address components
    address_info = response_data.get('address', {})
    address_additional_info = response_data.get('additionalInfo', {})
    firm = response_data.get('firm', '')

    # Build the standardized address dictionary
    standardized_address = {
        'firmname': firm,
        'street_address': address_info.get('streetAddress', ''),
        'address2': address_info.get('secondaryAddress', ''),
        'city': address_info.get('city', ''),
        'state': address_info.get('state', ''),
        'zip5': address_info.get('ZIPCode', ''),
        'zip4': address_info.get('ZIPPlus4', ''),
        'dp': address_additional_info.get('deliveryPoint', ''),
    }
    return standardized_address

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print(loop.run_until_complete(get_piece_tracking(sys.argv[1])))
