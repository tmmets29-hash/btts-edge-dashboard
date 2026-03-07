import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SPORT_KEY = "soccer_usa_mls"
KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"


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


def get_kalshi_btts_markets():
    try:
        r = requests.get(KALSHI_MARKETS_URL, timeout=20)
        r.raise_for_status()
        data = r.json()

        markets = data.get("markets", [])
        btts_markets = []

        for m in markets:
            title = str(m.get("title", "")).lower()
            subtitle = str(m.get("subtitle", "")).lower()
            rulebook = str(m.get("rulebook", "")).lower()

            blob = f"{title} {subtitle} {rulebook}"

            keywords = ["both teams", "btts", "both score"]

            if "mls" not in blob:
                continue

            if not any(k in blob for k in keywords):
                continue

            yes_price = m.get("yes_price")
            if yes_price is None:
                yes_price = m.get("yes_ask")

            btts_markets.append({
                "match": m.get("title", ""),
                "kalshi_price": yes_price,
                "ticker": m.get("ticker", "")
            })

        return btts_markets

    except Exception as e:
        return [{
            "match": "Kalshi API error",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "ERROR",
            "books": "",
            "notes": str(e)
        }]


def get_mls_events():
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"
        params = {"apiKey": ODDS_API_KEY}

        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
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

    kalshi_markets = get_kalshi_btts_markets()

    if not kalshi_markets:
        return [{
            "match": "No Kalshi BTTS markets found",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    if isinstance(kalshi_markets, list) and len(kalshi_markets) > 0:
        first = kalshi_markets[0]
        if first.get("signal") == "ERROR":
            return kalshi_markets

    events = get_mls_events()

    if not events:
        return [{
            "match": "No MLS events found from Odds API",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    results = []

    for event in events:
        home = str(event.get("home_team", ""))
        away = str(event.get("away_team", ""))
        event_name = f"{home} vs {away}"

        odds_data = get_btts_odds(event.get("id"))
        if not odds_data:
            continue

        best_row = None

        for book in odds_data.get("bookmakers", []):
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

                if yes_price is None or no_price is None:
                    continue

                prob_yes = odds_to_prob(yes_price)
                prob_no = odds_to_prob(no_price)

                if prob_yes is None or prob_no is None:
                    continue

                fair_yes = devig(prob_yes, prob_no)
                if fair_yes is None:
                    continue

                for km in kalshi_markets:
                    km_match = str(km.get("match", "")).lower()

                    if home.lower() in km_match and away.lower() in km_match:
                        kp = km.get("kalshi_price")

                        if kp is None:
                            continue

                        kalshi_price = float(kp) / 100.0
                        edge = fair_yes - kalshi_price
                        signal = "BET" if edge > 0.03 else "PASS"

                        row = {
                            "match": event_name,
                            "kalshi_price": round(kalshi_price * 100, 1),
                            "true_prob": round(fair_yes * 100, 1),
                            "edge": round(edge * 100, 1),
                            "signal": signal,
                            "books": book.get("title", ""),
                            "notes": km.get("ticker", "")
                        }

                        if best_row is None or row["edge"] > best_row["edge"]:
                            best_row = row

        if best_row is not None:
            results.append(best_row)

    if not results:
        return [{
            "match": "MLS games found but no Kalshi BTTS match",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO MATCH",
            "books": "",
            "notes": ""
        }]

    results.sort(key=lambda x: x["edge"], reverse=True)
    return results
