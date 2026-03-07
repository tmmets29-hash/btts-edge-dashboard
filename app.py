from flask import Flask, jsonify, render_template, request
from scanner import scan_btts_auto

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/healthz')
def healthz():
    return {'ok': True}


@app.route('/scan')
def scan():
    try:
        data = scan_btts_auto(
            edge_threshold=float(os.getenv('EDGE_THRESHOLD', '0.03')),
            bankroll=float(os.getenv('BANKROLL', '1000')),
            kelly_fraction=float(os.getenv('KELLY_FRACTION', '0.25')),
            max_events_per_sport=int(os.getenv('MAX_EVENTS_PER_SPORT', '8')),
        )
        return jsonify(data)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5001'))
    app.run(host='0.0.0.0', port=port, debug=False)
