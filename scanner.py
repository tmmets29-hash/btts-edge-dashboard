import os
import requests

ODDS_KEY = os.getenv("ODDS_API_KEY")

def scan_btts():

    sports = [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga"
    ]

    results = []

    for sport in sports:

        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"

        params = {
            "apiKey": ODDS_KEY,
            "markets": "btts",
            "regions": "uk"
        }

        r = requests.get(url, params=params)

        if r.status_code != 200:
            continue

        games = r.json()

        for g in games:

            match = g["home_team"] + " vs " + g["away_team"]

            for book in g["bookmakers"]:

                for market in book["markets"]:

                    if market["key"] != "btts":
                        continue

                    yes = None
                    no = None

                    for o in market["outcomes"]:

                        if o["name"].lower() == "yes":
                            yes = o["price"]

                        if o["name"].lower() == "no":
                            no = o["price"]

                    if not yes or not no:
                        continue

                    true_prob = 1/yes
                    kalshi_price = 0.50

                    edge = true_prob - kalshi_price

                    signal = "BET" if edge > 0.05 else "PASS"

                    results.append({
                        "match": match,
                        "kalshi_price": round(kalshi_price*100,1),
                        "true_prob": round(true_prob*100,1),
                        "edge": round(edge*100,1),
                        "signal": signal
                    })

    results.sort(key=lambda x: x["edge"], reverse=True)

    return results[:20]
