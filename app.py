from flask import Flask, jsonify
import requests

app = Flask(name)

@app.route('/gstinfo/<gst>', methods=['GET'])
def get_gst_info(gst):
    url = f"https://gst-return-status.p.rapidapi.com/free/gstin/{gst}"

    headers = {
        "x-rapidapi-key": "fe08d9b938msh1c558193d437622p1f800ajsn8193b63f2a58",
        "x-rapidapi-host": "gst-return-status.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers)
    try:
        data = response.json()
    except ValueError:
        data = {"error": "Invalid response from upstream API"}

    return jsonify(data)

if name == 'main':
    app.run(host='0.0.0.0', port=8080)
