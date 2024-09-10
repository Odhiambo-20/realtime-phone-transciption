import base64
import json
import os
from flask import Flask, request, Response
from flask_sock import Sock
from pyngrok import ngrok, exception
from twilio.rest import Client
from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException

from twilio_transcriber import TwilioTranscriber

# Load environment variables
load_dotenv()

# Flask settings
PORT = 5000
DEBUG = False
INCOMING_CALL_ROUTE = '/'
WEBSOCKET_ROUTE = '/realtime'

# Twilio authentication
account_sid = os.environ['TWILIO_ACCOUNT_SID']
api_key = os.environ['TWILIO_API_KEY_SID']
api_secret = os.environ['TWILIO_API_SECRET']
client = Client(api_key, api_secret, account_sid)

# Twilio phone number to call
TWILIO_NUMBER = os.environ['TWILIO_NUMBER']

# ngrok authentication
ngrok.set_auth_token(os.getenv("NGROK_AUTHTOKEN"))

# Create Flask app
app = Flask(__name__)
sock = Sock(app)

@app.route(INCOMING_CALL_ROUTE, methods=['GET', 'POST'])
def receive_call():
    if request.method == 'POST':
        xml = f"""
<Response>
    <Say>
        Speak to see your speech transcribed in the console
    </Say>
    <Connect>
        <Stream url='wss://{request.host}{WEBSOCKET_ROUTE}' />
    </Connect>
</Response>
""".strip()
        return Response(xml, mimetype='text/xml')
    else:
        return "Real-time phone call transcription app"

@sock.route(WEBSOCKET_ROUTE)
def transcription_websocket(ws):
    transcriber = None
    while True:
        data = json.loads(ws.receive())
        match data['event']:
            case "connected":
                transcriber = TwilioTranscriber()
                transcriber.connect()
                print('Transcriber connected')
            case "start":
                print('Twilio started')
            case "media":
                payload_b64 = data['media']['payload']
                payload_mulaw = base64.b64decode(payload_b64)
                if transcriber:
                    transcriber.stream(payload_mulaw)
            case "stop":
                print('Twilio stopped')
                if transcriber:
                    transcriber.close()
                print('Transcriber closed')

if __name__ == "__main__":
    listener = None
    try:
        # Open Ngrok tunnel
        listener = ngrok.connect(PORT)
        print(f"Ngrok tunnel opened at {listener.public_url} for port {PORT}")
        NGROK_URL = listener.public_url

        # Set ngrok URL as the webhook for the Twilio number
        twilio_numbers = client.incoming_phone_numbers.list()

        # Debug: print the Twilio numbers and their format
        for num in twilio_numbers:
            print(f"Number: {num.phone_number}, SID: {num.sid}")

        # Try to find the correct Twilio number SID
        twilio_number_sid = None
        for num in twilio_numbers:
            if num.phone_number == TWILIO_NUMBER:  # Ensure the correct number format
                twilio_number_sid = num.sid
                break

        if twilio_number_sid:
            try:
                client.incoming_phone_numbers(twilio_number_sid).update(
                    voice_url=f"{NGROK_URL}{INCOMING_CALL_ROUTE}"
                )
                print(f"Webhook updated for number {TWILIO_NUMBER}")
            except TwilioRestException as e:
                print(f"Failed to update Twilio number: {e}")
        else:
            print(f"No matching Twilio number found for {TWILIO_NUMBER}")

        # Run the Flask app
        app.run(port=PORT, debug=DEBUG)

    except exception.PyngrokNgrokError as e:
        print(f"Ngrok error: {e}")
    
    finally:
        # Always disconnect the ngrok tunnel on exit
        if listener:
            ngrok.disconnect(listener.public_url)
