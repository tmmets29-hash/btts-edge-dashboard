import os
import requests

ODDS_KEY = os.getenv("ODDS_API_KEY")

def american_to_prob(price):
    try:
        price = float(price)
        if price > 0:
            return 100 / (price + 100)
        return abs(price) / (abs(price) + 100)
    except Exception:
        return None

def decimal_to_prob(price):
    try:
        price = float(price)
        if price <= 1:
            return None
        return 1 / price
    except Exception:
        return None

def scan_btts():
    sports = [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league"
    ]

    results = []

    if not ODDS_KEY:
        return [{
            "match": "Missing ODDS_API_KEY",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "CHECK ENV"
        }]

    for sport in sports:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
        params = {
            "apiKey": ODDS_KEY,
            "regions": "us,uk,eu",
            "markets": "h2h"
        }

        try:
            r = requests.get(url, params=params, timeout=20)

            if r.status_code != 200:
                results.append({
                    "match": f"{sport} API {r.status_code}",
                    "kalshi_price": "-",
                    "true_prob": "-",
                    "edge": "-",
                    "signal": "API ERROR"
                })
                continue

            games = r.json()

            if not games:
                results.append({
                    "match": f"{sport} returned no games",
                    "kalshi_price": "-",
                    "true_prob": "-",
                    "edge": "-",
                    "signal": "NO DATA"
                })
                continue

            found_market = False

            for g in games:
                match = f"{g.get('home_team', '')} vs {g.get('away_team', '')}"

                for book in g.get("bookmakers", []):
                    for market in book.get("markets", []):
                        if market.get("key") != "btts":
                            continue

                        found_market = True
                        yes_price = None
                        no_price = None

                        for o in market.get("outcomes", []):
                            name = str(o.get("name", "")).lower()
                            price = o.get("price")

                            if name == "yes":
                                yes_price = price
                            elif name == "no":
                                no_price = price

                        if yes_price is None or no_price is None:
                            continue

                        yes_prob = decimal_to_prob(yes_price)
                        no_prob = decimal_to_prob(no_price)

                        if yes_prob is None or no_prob is None:
                            yes_prob = american_to_prob(yes_price)
                            no_prob = american_to_prob(no_price)

                        if yes_prob is None or no_prob is None:
                            continue

                        overround = yes_prob + no_prob
                        if overround <= 0:
                            continue

                        true_prob = yes_prob / overround
                        kalshi_price = 0.50
                        edge = true_prob - kalshi_price
                        signal = "BET" if edge > 0.05 else "PASS"

                        results.append({
                            "match": match,
                            "kalshi_price": round(kalshi_price * 100, 1),
                            "true_prob": round(true_prob * 100, 1),
                            "edge": round(edge * 100, 1),
                            "signal": signal
                        })

            if not found_market:
                results.append({
                    "match": f"{sport} had games but no BTTS market",
                    "kalshi_price": "-",
                    "true_prob": "-",
                    "edge": "-",
                    "signal": "NO BTTS"
                })

        except Exception as e:
            results.append({
                "match": f"{sport} exception: {str(e)[:60]}",
                "kalshi_price": "-",
                "true_prob": "-",
                "edge": "-",
                "signal": "ERROR"
            })

    results.sort(key=lambda x: str(x["signal"]))
    return results[:50]
