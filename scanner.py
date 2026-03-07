import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SPORT_KEY = "soccer_usa_mls"


def odds_to_prob(price):
    price = float(price)
    return 1 / price


def devig(p_yes, p_no):
    total = p_yes + p_no
    return p_yes / total


def get_mls_events():

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"

    r = requests.get(url, params={"apiKey": ODDS_API_KEY})

    if r.status_code != 200:
        return []

    return r.json()


def get_btts_odds(event_id):

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{event_id}/odds"

    params = {
        "apiKey": ODDS_API_KEY,
        "markets": "btts",
        "regions": "us,uk,eu"
    }

    r = requests.get(url, params=params)

    if r.status_code != 200:
        return None

    return r.json()


def scan_btts():

    events = get_mls_events()

    results = []

    for event in events:

        home = event["home_team"]
        away = event["away_team"]

        odds = get_btts_odds(event["id"])

        if not odds:
            continue

        for book in odds["bookmakers"]:

            for market in book["markets"]:

                if market["key"] != "btts":
                    continue

                yes_odds = None
                no_odds = None

                for outcome in market["outcomes"]:

                    if outcome["name"].lower() == "yes":
                        yes_odds = outcome["price"]

                    if outcome["name"].lower() == "no":
                        no_odds = outcome["price"]

                if yes_odds and no_odds:

                    p_yes = odds_to_prob(yes_odds)
                    p_no = odds_to_prob(no_odds)

                    fair_prob = devig(p_yes, p_no)

                    results.append({
                        "match": f"{home} vs {away}",
                        "sportsbook_yes_odds": yes_odds,
                        "sportsbook_prob": round(fair_prob * 100, 1),
                        "books": book["title"]
                    })

    return results
