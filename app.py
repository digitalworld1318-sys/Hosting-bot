from flask import Flask, jsonify, request
import requests
import os
import time
from datetime import datetime, timedelta

app = Flask(__name__)

# API key from environment variable (Render pe set karna)
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'fe08d9b938msh1c558193d437622p1f800ajsn8193b63f2a58')

# Simple cache dictionary: {gst: {'data': response_data, 'expiry': timestamp}}
cache = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache

@app.route('/gst', methods=['GET'])
def get_gst_info():
    start_time = time.time()
    
    # Get GST number from query parameter
    gst = request.args.get('id')
    if not gst:
        return jsonify({
            "status": "error",
            "code": 400,
            "message": "Missing 'id' parameter. Use ?id=27AAPFU0939F1ZV"
        }), 400
    
    # Check cache
    cached_data = None
    is_cached = False
    if gst in cache:
        data_entry = cache[gst]
        if datetime.now() < data_entry['expiry']:
            cached_data = data_entry['data']
            is_cached = True
    
    if cached_data:
        api_response = cached_data
    else:
        # Call external API
        url = f"https://gst-return-status.p.rapidapi.com/free/gstin/{gst}"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "gst-return-status.p.rapidapi.com"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            api_response = response.json()
            
            # Store in cache if success
            if api_response.get('success', False):
                cache[gst] = {
                    'data': api_response,
                    'expiry': datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)
                }
        except Exception as e:
            api_response = {"success": False, "error": str(e)}
    
    # Calculate response time
    response_time_ms = int((time.time() - start_time) * 1000)
    
    # Determine overall status
    if api_response.get('success', False):
        status = "success"
        code = 200
    else:
        status = "error"
        code = 500
        # You can change code to 404 if GST not found, but API returns success false
    
    # Build final response
    final_response = {
        "status": status,
        "code": code,
        "searched_gst-id": gst,   # Here vehicle means GST number
        "response_time": f"{response_time_ms}ms",
        "cached": is_cached,
        "data": api_response,
        "credit": "@Z4X_Silent_Boy",
        "Owner": "KEY BUY FROM OWNER @Z4X_Silent_Boy",
        "channel": "https://t.me/DigitalWorld1318"
    }
    
    return jsonify(final_response), code

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
