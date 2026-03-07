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


def devig_two_way(prob_a, prob_b):
    total = prob_a + prob_b
    if total <= 0:
        return None, None
    return prob_a / total, prob_b / total


def devig_three_way(prob_a, prob_b, prob_c):
    total = prob_a + prob_b + prob_c
    if total <= 0:
        return None, None, None
    return prob_a / total, prob_b / total, prob_c / total


def get_mls_events():
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"
        r = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=20)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def get_event_odds(event_id):
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{event_id}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "markets": "btts,totals,h2h",
            "regions": "us,uk,eu",
            "oddsFormat": "decimal",
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
            "market": "-",
            "side": "-",
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
            "market": "-",
            "side": "-",
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

        odds = get_event_odds(event.get("id"))
        if not odds:
            continue

        bookmakers = odds.get("bookmakers", [])

        # -------------------------
        # 1. BTTS
        # -------------------------
        best_btts_yes = None
        best_btts_no = None
        best_btts_yes_book = ""
        best_btts_no_book = ""

        for book in bookmakers:
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
                    if best_btts_yes is None or float(yes_price) > float(best_btts_yes):
                        best_btts_yes = float(yes_price)
                        best_btts_yes_book = book.get("title", "")

                if no_price is not None:
                    if best_btts_no is None or float(no_price) > float(best_btts_no):
                        best_btts_no = float(no_price)
                        best_btts_no_book = book.get("title", "")

        if best_btts_yes is not None and best_btts_no is not None:
            prob_yes = odds_to_prob(best_btts_yes)
            prob_no = odds_to_prob(best_btts_no)

            if prob_yes is not None and prob_no is not None:
                fair_yes, fair_no = devig_two_way(prob_yes, prob_no)

                if fair_yes is not None:
                    results.append({
                        "match": match_name,
                        "market": "BTTS",
                        "side": "YES",
                        "kalshi_price": "-",
                        "true_prob": round(fair_yes * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"YES: {best_btts_yes_book} | NO: {best_btts_no_book}",
                        "notes": f"Best YES {best_btts_yes}, Best NO {best_btts_no}"
                    })

                if fair_no is not None:
                    results.append({
                        "match": match_name,
                        "market": "BTTS",
                        "side": "NO",
                        "kalshi_price": "-",
                        "true_prob": round(fair_no * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"YES: {best_btts_yes_book} | NO: {best_btts_no_book}",
                        "notes": f"Best YES {best_btts_yes}, Best NO {best_btts_no}"
                    })

        # -------------------------
        # 2. TOTALS 2.5
        # -------------------------
        best_over = None
        best_under = None
        best_over_book = ""
        best_under_book = ""

        for book in bookmakers:
            for market in book.get("markets", []):
                if market.get("key") != "totals":
                    continue

                # only use totals line 2.5
                market_point = market.get("point")
                if market_point is None or float(market_point) != 2.5:
                    continue

                over_price = None
                under_price = None

                for outcome in market.get("outcomes", []):
                    name = str(outcome.get("name", "")).lower()
                    price = outcome.get("price")

                    if name == "over":
                        over_price = price
                    elif name == "under":
                        under_price = price

                if over_price is not None:
                    if best_over is None or float(over_price) > float(best_over):
                        best_over = float(over_price)
                        best_over_book = book.get("title", "")

                if under_price is not None:
                    if best_under is None or float(under_price) > float(best_under):
                        best_under = float(under_price)
                        best_under_book = book.get("title", "")

        if best_over is not None and best_under is not None:
            prob_over = odds_to_prob(best_over)
            prob_under = odds_to_prob(best_under)

            if prob_over is not None and prob_under is not None:
                fair_over, fair_under = devig_two_way(prob_over, prob_under)

                if fair_over is not None:
                    results.append({
                        "match": match_name,
                        "market": "TOTALS 2.5",
                        "side": "OVER",
                        "kalshi_price": "-",
                        "true_prob": round(fair_over * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"OVER: {best_over_book} | UNDER: {best_under_book}",
                        "notes": f"Best OVER {best_over}, Best UNDER {best_under}"
                    })

                if fair_under is not None:
                    results.append({
                        "match": match_name,
                        "market": "TOTALS 2.5",
                        "side": "UNDER",
                        "kalshi_price": "-",
                        "true_prob": round(fair_under * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"OVER: {best_over_book} | UNDER: {best_under_book}",
                        "notes": f"Best OVER {best_over}, Best UNDER {best_under}"
                    })

        # -------------------------
        # 3. H2H / MONEYLINE
        # -------------------------
        best_home = None
        best_draw = None
        best_away = None
        best_home_book = ""
        best_draw_book = ""
        best_away_book = ""

        for book in bookmakers:
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue

                home_price = None
                draw_price = None
                away_price = None

                for outcome in market.get("outcomes", []):
                    name = str(outcome.get("name", "")).strip()
                    price = outcome.get("price")

                    if name == home:
                        home_price = price
                    elif name == away:
                        away_price = price
                    elif name.lower() == "draw":
                        draw_price = price

                if home_price is not None:
                    if best_home is None or float(home_price) > float(best_home):
                        best_home = float(home_price)
                        best_home_book = book.get("title", "")

                if draw_price is not None:
                    if best_draw is None or float(draw_price) > float(best_draw):
                        best_draw = float(draw_price)
                        best_draw_book = book.get("title", "")

                if away_price is not None:
                    if best_away is None or float(away_price) > float(best_away):
                        best_away = float(away_price)
                        best_away_book = book.get("title", "")

        if best_home is not None and best_draw is not None and best_away is not None:
            prob_home = odds_to_prob(best_home)
            prob_draw = odds_to_prob(best_draw)
            prob_away = odds_to_prob(best_away)

            if prob_home and prob_draw and prob_away:
                fair_home, fair_draw, fair_away = devig_three_way(prob_home, prob_draw, prob_away)

                if fair_home is not None:
                    results.append({
                        "match": match_name,
                        "market": "MONEYLINE",
                        "side": "HOME",
                        "kalshi_price": "-",
                        "true_prob": round(fair_home * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"HOME: {best_home_book} | DRAW: {best_draw_book} | AWAY: {best_away_book}",
                        "notes": f"Best HOME {best_home}, DRAW {best_draw}, AWAY {best_away}"
                    })

                if fair_draw is not None:
                    results.append({
                        "match": match_name,
                        "market": "MONEYLINE",
                        "side": "DRAW",
                        "kalshi_price": "-",
                        "true_prob": round(fair_draw * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"HOME: {best_home_book} | DRAW: {best_draw_book} | AWAY: {best_away_book}",
                        "notes": f"Best HOME {best_home}, DRAW {best_draw}, AWAY {best_away}"
                    })

                if fair_away is not None:
                    results.append({
                        "match": match_name,
                        "market": "MONEYLINE",
                        "side": "AWAY",
                        "kalshi_price": "-",
                        "true_prob": round(fair_away * 100, 1),
                        "edge": "-",
                        "signal": "BOOK ONLY",
                        "books": f"HOME: {best_home_book} | DRAW: {best_draw_book} | AWAY: {best_away_book}",
                        "notes": f"Best HOME {best_home}, DRAW {best_draw}, AWAY {best_away}"
                    })

    if not results:
        return [{
            "match": "No usable MLS markets found",
            "market": "-",
            "side": "-",
            "kalshi_price": "-",
            "true_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    results.sort(key=lambda x: (x["match"], x["market"], x["side"]))
    return results
