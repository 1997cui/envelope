from flask import Flask, render_template, request, make_response
import imb
import config
import pdfkit

app = Flask(__name__)


def generate_human_readable(receipt_zip: int, serial: int):
    return "{0:02d}-{1:03d}-{2:d}-{3:06d}-{4:d}".format(config.BARCODE_ID, config.SRV_TYPE, config.MAILER_ID, serial, receipt_zip)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    sender_address = request.form['sender_address']
    recipient_address = request.form['recipient_address']
    try:
        receipt_zip = int(request.form['receipt_zip'])
        serial = int(request.form['serial'])
    except:
        response = "Serial number or receipt zip is not number!"
        return response
    html = render_template('envelopepdf.html', sender_address=sender_address, recipient_address=recipient_address, 
                           human_readable_bar=generate_human_readable(receipt_zip, serial), 
                           barcode=imb.encode(config.BARCODE_ID, config.SRV_TYPE, config.MAILER_ID, serial, str(receipt_zip)))
    if 'htmlgenerate' in request.form:
        return html
    if 'pdfgenerate' in request.form:
        options={
            'page-height': '4.125in',
            'page-width': '9.5in',
            'margin-bottom' : '0in',
            'margin-top': '0in',
            'margin-left': '0in',
            'margin-right': '0in',
            'disable-smart-shrinking': '',
        }
        pdf = pdfkit.from_string(html, False, options=options)
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=envelope.pdf'
        return response
    return "Empty"

if __name__ == '__main__':
    app.run(debug=True)