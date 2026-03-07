from flask import Flask, render_template, jsonify
from scanner import scan_btts

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scan")
def scan():
    return jsonify(scan_btts())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
