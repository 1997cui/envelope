from quart import render_template, request, make_response, jsonify, session
from . import imb
from . import config
import pdfkit
from . import usps_api
from . import app
import datetime
import aioredis

ROLLING_WINDOW = 50

redis_client = aioredis.Redis(host='localhost', port=6379, db=0)
async def generate_serial():
    today = datetime.datetime.today()
    num_days = (today - datetime.datetime(1970,1,1)).days
    base = num_days % ROLLING_WINDOW
    day_key = "serial_" + str(base)
    perday_counter = await redis_client.incr(day_key)
    if perday_counter >= 9999:
        raise ValueError
    await redis_client.expire(day_key, 48 * 60 * 60)
    return base * 10000 + int(perday_counter)

def generate_human_readable(receipt_zip: str, serial: int):
    return "{0:02d}-{1:03d}-{2:d}-{3:06d}-{4:s}".format(config.BARCODE_ID, config.SRV_TYPE, config.MAILER_ID, serial, receipt_zip)

def query_usps_tracking(receipt_zip: str, serial: int):
    imb = generate_human_readable(receipt_zip, serial)
    imb = imb.replace('-', '')
    app.add_background_task(usps_api.token_maintain)
    return usps_api.get_piece_tracking(imb)

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/generate', methods=['POST'])
async def generate():
    sender_address = (await request.form)['sender_address']
    recipient_name = (await request.form)['recipient_name']
    recipient_company = (await request.form).get('recipient_company', '')
    recipient_street = (await request.form)['recipient_street']
    recipient_address2 = (await request.form).get('recipient_address2', '')
    recipient_city = (await request.form)['recipient_city']
    recipient_state = (await request.form)['recipient_state']
    try:
        recipient_zip = int((await request.form)['recipient_zip'])
        recipient_zip = str((await request.form)['recipient_zip'])
    except:
        response = "Recipient zip is not number!"
        return response
    if len(str((await request.form)['recipient_zip'])) < 5:
        response = "Invalid recipient zip"
        return response
    zip = zip5 = str((await request.form)['recipient_zip'])[:5]
    if len(str((await request.form)['recipient_zip'])) > 5:
        zip4 = str((await request.form)['recipient_zip'])[5:9]
        zip = f"{zip5}-{zip4}"
    recipient_address_parts = [
        recipient_name,
        recipient_company,
        recipient_street,
        recipient_address2,
        f"{recipient_city}, {recipient_state}, {zip}"
    ]
    recipient_address = '\n'.join(filter(bool, recipient_address_parts))
    serial = await generate_serial()
    session['sender_address'] = sender_address
    session['recipient_address'] = recipient_address
    session['serial'] = serial
    session['recipient_zip'] = str((await request.form)['recipient_zip'])
    return await render_template('generate.html', serial=serial, recipient_zip=recipient_zip)

@app.route('/download/<format_type>/<doc_type>')
async def download(format_type: str, doc_type: str):
    sender_address = session['sender_address']
    recipient_address = session['recipient_address']
    serial = session['serial']
    recipient_zip = session['recipient_zip']
    human_readable_bar = generate_human_readable(recipient_zip, serial)
    row = request.args.get('row', default=1, type=int)
    col = request.args.get('col', default=1, type=int)
    barcode = imb.encode(config.BARCODE_ID, config.SRV_TYPE, config.MAILER_ID, serial, str(recipient_zip))

    if format_type == 'envelope':
        template_name = 'envelopepdf.html'

    elif format_type == 'avery':
        template_name = 'avery8163.html'

    else:
        return "Format type not valid"

    html = await render_template(template_name, sender_address=sender_address, recipient_address=recipient_address,
                           human_readable_bar=human_readable_bar, barcode=barcode, row=row, col=col)

    if doc_type == 'html':
        return html
    elif doc_type == 'pdf':
        if format_type == 'envelope':
            options = {
                'page-height': '4.125in',
                'page-width': '9.5in',
                'margin-bottom': '0in',
                'margin-top': '0in',
                'margin-left': '0in',
                'margin-right': '0in',
                'disable-smart-shrinking': '',
            }
        elif format_type == 'avery':
            options = {
                'page-height': '11in',
                'page-width': '8.5in',
                'margin-bottom': '0in',
                'margin-top': '0in',
                'margin-left': '0in',
                'margin-right': '0in',
                'disable-smart-shrinking': '',
            }

        pdf = pdfkit.from_string(html, False, options=options)
        response = await make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={format_type}.pdf'
        return response
    else:
        return "Document type not valid"

@app.route('/track', methods=['POST'])
async def track():
    try:
        receipt_zip = int((await request.form)['receipt_zip'])
        receipt_zip = str((await request.form)['receipt_zip'])
        serial = int((await request.form)['serial'])
    except:
        response = "Serial number or receipt zip is not number!"
        return response
    result = await query_usps_tracking(receipt_zip, serial)
    if 'error' in result:
        message = "{}: {}. Details: {}".format(result['error'], result['error_description'], result['details'])
        return await render_template("tracking.html", error_message=message)
    elif 'message' in result and result['message']:
        return await render_template("tracking.html", error_message=result['message'])
    else:
        return await render_template("tracking.html", data=result['data'])

@app.route('/validate_address', methods=['POST'])
async def validate_address():
    zip = str((await request.form)['zip'])
    zip5 = zip[:5]
    address = {
        'address1': (await request.form)['address1'],
        'address2': (await request.form)['address2'],
        'city': (await request.form)['city'],
        'state': (await request.form)['state'],
        'zip5': zip5,
    }
    if len(zip) >= 9:
        address['zip4'] = zip[5:9]
    if len(zip) >= 11:
        address['dp'] = zip[9:11]
    if len((await request.form)['firmname']) > 0:
        address['firmname'] = (await request.form)['firmname']
    standardized_address = await usps_api.get_USPS_standardized_address(address)
    
    return jsonify(standardized_address)