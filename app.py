from flask import Flask, jsonify, request
import requests
import os

app = Flask(__name__)

# API key ko environment variable se lena better hai, ya direct rakh sakte hain
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'fe08d9b938msh1c558193d437622p1f800ajsn8193b63f2a58')

@app.route('/gst', methods=['GET'])
def get_gst_info():
    # Query parameter se GST number lena
    gst = request.args.get('id')
    
    if not gst:
        return jsonify({"error": "Missing 'id' parameter. Use ?id=27AAPFU0939F1ZV"}), 400
    
    url = f"https://gst-return-status.p.rapidapi.com/free/gstin/{gst}"
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "gst-return-status.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
    except requests.exceptions.RequestException as e:
        data = {"error": f"Request failed: {str(e)}"}
    except ValueError:
        data = {"error": "Invalid response from upstream API"}
    
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
