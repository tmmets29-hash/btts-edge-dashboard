from flask import Flask, jsonify, render_template, request
from scanner import scan_btts
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return {'ok': True}

@app.route('/api/scan')
def api_scan():
    leagues_raw = request.args.get('leagues', '').strip()
    leagues = [x.strip() for x in leagues_raw.split(',') if x.strip()] if leagues_raw else None
    try:
        payload = scan_btts(leagues=leagues)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5001'))
    app.run(host='0.0.0.0', port=port, debug=False)
