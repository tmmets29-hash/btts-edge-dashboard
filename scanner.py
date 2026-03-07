import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORT_KEY = "soccer_usa_mls"


def odds_to_prob(price):
    try:
        price = float(price)
        if price <= 1:
            return None
        return 1 / price
    except Exception:
        return None


def devig(prob_yes, prob_no):
    total = prob_yes + prob_no
    if total <= 0:
        return None
    return prob_yes / total


def get_mls_events():
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"
        r = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=20)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def get_btts_odds(event_id):
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{event_id}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "markets": "btts",
            "regions": "us,uk,eu",
            "oddsFormat": "decimal"
        }
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def scan_btts():
    if not ODDS_API_KEY:
        return [{
            "match": "Missing ODDS_API_KEY",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "CHECK ENV",
            "books": "",
            "notes": ""
        }]

    events = get_mls_events()

    if not events:
        return [{
            "match": "No MLS events found",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    results = []

    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        match_name = f"{home} vs {away}"

        odds = get_btts_odds(event.get("id"))
        if not odds:
            continue

        best_yes = None
        best_no = None
        best_yes_book = ""
        best_no_book = ""

        for book in odds.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") != "btts":
                    continue

                yes_price = None
                no_price = None

                for outcome in market.get("outcomes", []):
                    name = str(outcome.get("name", "")).lower()
                    price = outcome.get("price")

                    if name == "yes":
                        yes_price = price
                    elif name == "no":
                        no_price = price

                if yes_price is not None:
                    if best_yes is None or float(yes_price) > float(best_yes):
                        best_yes = float(yes_price)
                        best_yes_book = book.get("title", "")

                if no_price is not None:
                    if best_no is None or float(no_price) > float(best_no):
                        best_no = float(no_price)
                        best_no_book = book.get("title", "")

        if best_yes is None or best_no is None:
            continue

        prob_yes = odds_to_prob(best_yes)
        prob_no = odds_to_prob(best_no)

        if prob_yes is None or prob_no is None:
            continue

        fair_prob = devig(prob_yes, prob_no)
        if fair_prob is None:
            continue

        results.append({
            "match": match_name,
            "kalshi_price": "-",
            "true_prob": round(fair_prob * 100, 1),
            "edge": "-",
            "signal": "BOOK ONLY",
            "books": f"YES: {best_yes_book} | NO: {best_no_book}",
            "notes": f"Best YES {best_yes}, Best NO {best_no}"
        })

    if not results:
        return [{
            "match": "No MLS BTTS odds found",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    results.sort(key=lambda x: x["match"])
    return results
