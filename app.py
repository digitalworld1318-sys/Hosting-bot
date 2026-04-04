from flask import Flask, jsonify, request
import requests
import os
import time
from datetime import datetime, timedelta

app = Flask(__name__)

RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'fe08d9b938msh1c558193d437622p1f800ajsn8193b63f2a58')

# Simple cache
cache = {}
CACHE_TTL_SECONDS = 3600

@app.route('/gst', methods=['GET'])
def get_gst_info():
    start_time = time.time()
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
        entry = cache[gst]
        if datetime.now() < entry['expiry']:
            cached_data = entry['data']
            is_cached = True
    
    if cached_data:
        api_response = cached_data
    else:
        url = f"https://gst-return-status.p.rapidapi.com/free/gstin/{gst}"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "gst-return-status.p.rapidapi.com"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            api_response = response.json()
            if api_response.get('success', False):
                cache[gst] = {
                    'data': api_response,
                    'expiry': datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)
                }
        except Exception as e:
            api_response = {"success": False, "error": str(e)}
    
    # Calculate response time
    response_time_ms = int((time.time() - start_time) * 1000)
    
    # Prepare final response - avoid double data
    if api_response.get('success', False):
        # Extract inner data from API response
        gst_data = api_response.get('data', {})
        final_response = {
            "status": "success",
            "code": 200,
            "searched_gst-id": gst,
            "response_time": f"{response_time_ms}ms",
            "cached": is_cached,
            "success": True,  # API's success flag
            "data": gst_data,  # Direct GST data, not nested again
            "credit": "@DigitalWorld1318",
            "Owner": "@Z4X_Silent_Boy",
            "channel": "https://youtube.com/@digitalworld1318"
        }
        http_code = 200
    else:
        final_response = {
            "status": "error",
            "code": 500,
            "searched_gst-id": gst,
            "response_time": f"{response_time_ms}ms",
            "cached": is_cached,
            "success": False,
            "error": api_response.get('error', 'Unknown error'),
            "credit": "@DigitalWorld1318",
            "Owner": "@Z4X_Silent_Boy",
            "channel": "https://youtube.com/@digitalworld1318"
        }
        http_code = 500
    
    return jsonify(final_response), http_code

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
