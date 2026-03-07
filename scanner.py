import requests
import os

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SPORT_KEY = "soccer_usa_mls"

KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"


def get_kalshi_btts_markets():
    try:
        r = requests.get(KALSHI_MARKETS_URL)
        markets = r.json()["markets"]

        btts_markets = []

        for m in markets:
            title = m.get("title", "").lower()

            keywords = ["both teams", "btts", "both score"]

if any(k in title for k in keywords):
                btts_markets.append({
                    "match": m.get("title"),
                    "kalshi_price": m.get("yes_price"),
                    "ticker": m.get("ticker")
                })

        return btts_markets

    except Exception as e:
        return [{
            "match": "Kalshi API error",
            "signal": "ERROR",
            "notes": str(e)
        }]


def get_mls_games():

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"

    params = {
        "apiKey": ODDS_API_KEY
    }

    r = requests.get(url, params=params)
    return r.json()


def get_btts_odds(event_id):

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{event_id}/odds"

    params = {
        "apiKey": ODDS_API_KEY,
        "markets": "btts",
        "regions": "us"
    }

    r = requests.get(url, params=params)
    return r.json()


def devig(prob_yes, prob_no):

    total = prob_yes + prob_no

    return prob_yes / total


def odds_to_prob(price):

    return 1 / price


def scan_btts():

    results = []

    kalshi_markets = get_kalshi_btts_markets()

    if not kalshi_markets:
        return [{
            "match": "No Kalshi BTTS markets found",
            "signal": "NO DATA"
        }]

    events = get_mls_games()

    for event in events:

        home = event["home_team"]
        away = event["away_team"]

        event_name = f"{home} vs {away}"

        odds_data = get_btts_odds(event["id"])

        for book in odds_data.get("bookmakers", []):

            for market in book["markets"]:

                if market["key"] != "btts":
                    continue

                outcomes = market["outcomes"]

                yes_price = None
                no_price = None

                for o in outcomes:

                    if o["name"].lower() == "yes":
                        yes_price = o["price"]

                    if o["name"].lower() == "no":
                        no_price = o["price"]

                if yes_price and no_price:

                    prob_yes = odds_to_prob(yes_price)
                    prob_no = odds_to_prob(no_price)

                    true_prob = devig(prob_yes, prob_no)

                    for km in kalshi_markets:

                        if home.lower() in km["match"].lower() and away.lower() in km["match"].lower():

                            kalshi_price = km["kalshi_price"] / 100

                            edge = true_prob - kalshi_price

                            signal = "BET" if edge > 0.03 else "PASS"

                            results.append({
                                "match": event_name,
                                "kalshi_price": round(kalshi_price, 3),
                                "true_prob": round(true_prob, 3),
                                "edge": round(edge, 3),
                                "signal": signal,
                                "books": book["title"]
                            })

    if not results:
        return [{
            "match": "MLS games found but no Kalshi BTTS match",
            "signal": "NO MATCH"
        }]

    return results
