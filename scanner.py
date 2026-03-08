import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORT_KEY = "soccer_usa_mls"
LEAGUE_LABEL = "MLS"


def odds_to_prob(price):
    try:
        price = float(price)
        if price <= 1:
            return None
        return 1 / price
    except Exception:
        return None


def devig_two_way(a, b):
    total = a + b
    if total <= 0:
        return None, None
    return a / total, b / total


def devig_three_way(a, b, c):
    total = a + b + c
    if total <= 0:
        return None, None, None
    return a / total, b / total, c / total


def classify_edge(edge):
    if edge is None:
        return "NO DATA"
    if edge >= 0.04:
        return "BET"
    if edge >= 0.02:
        return "WATCH"
    return "PASS"


def get_league_odds():
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h,totals,btts",
            "oddsFormat": "decimal",
        }
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def best_price_for_outcome(bookmakers, market_key, outcome_name, point=None):
    best_price = None
    best_book = ""

    for book in bookmakers:
        for market in book.get("markets", []):
            if market.get("key") != market_key:
                continue

            if point is not None:
                if market.get("point") is None or float(market.get("point")) != float(point):
                    continue

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).strip().lower()
                if name != outcome_name.strip().lower():
                    continue

                price = outcome.get("price")
                if price is None:
                    continue

                if best_price is None or float(price) > float(best_price):
                    best_price = float(price)
                    best_book = book.get("title", "")

    if best_price is None:
        return None

    implied = odds_to_prob(best_price)
    if implied is None:
        return None

    return {
        "price": best_price,
        "book": best_book,
        "implied_prob": implied
    }


def consensus_btts(bookmakers):
    yes_probs = []
    no_probs = []

    for book in bookmakers:
        for market in book.get("markets", []):
            if market.get("key") != "btts":
                continue

            yes_price = None
            no_price = None

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).strip().lower()
                price = outcome.get("price")

                if name == "yes":
                    yes_price = price
                elif name == "no":
                    no_price = price

            if yes_price is None or no_price is None:
                continue

            py = odds_to_prob(yes_price)
            pn = odds_to_prob(no_price)
            if py is None or pn is None:
                continue

            fy, fn = devig_two_way(py, pn)
            if fy is None or fn is None:
                continue

            yes_probs.append(fy)
            no_probs.append(fn)

    if not yes_probs or not no_probs:
        return None

    return {
        "yes": sum(yes_probs) / len(yes_probs),
        "no": sum(no_probs) / len(no_probs),
    }


def consensus_totals_25(bookmakers):
    over_probs = []
    under_probs = []

    for book in bookmakers:
        for market in book.get("markets", []):
            if market.get("key") != "totals":
                continue
            if market.get("point") is None or float(market.get("point")) != 2.5:
                continue

            over_price = None
            under_price = None

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).strip().lower()
                price = outcome.get("price")

                if name == "over":
                    over_price = price
                elif name == "under":
                    under_price = price

            if over_price is None or under_price is None:
                continue

            po = odds_to_prob(over_price)
            pu = odds_to_prob(under_price)
            if po is None or pu is None:
                continue

            fo, fu = devig_two_way(po, pu)
            if fo is None or fu is None:
                continue

            over_probs.append(fo)
            under_probs.append(fu)

    if not over_probs or not under_probs:
        return None

    return {
        "over": sum(over_probs) / len(over_probs),
        "under": sum(under_probs) / len(under_probs),
    }


def consensus_moneyline(bookmakers, home_team, away_team):
    home_probs = []
    draw_probs = []
    away_probs = []

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

                if name == home_team:
                    home_price = price
                elif name == away_team:
                    away_price = price
                elif name.lower() == "draw":
                    draw_price = price

            if home_price is None or draw_price is None or away_price is None:
                continue

            ph = odds_to_prob(home_price)
            pd = odds_to_prob(draw_price)
            pa = odds_to_prob(away_price)
            if ph is None or pd is None or pa is None:
                continue

            fh, fd, fa = devig_three_way(ph, pd, pa)
            if fh is None or fd is None or fa is None:
                continue

            home_probs.append(fh)
            draw_probs.append(fd)
            away_probs.append(fa)

    if not home_probs:
        return None

    return {
        "home": sum(home_probs) / len(home_probs),
        "draw": sum(draw_probs) / len(draw_probs),
        "away": sum(away_probs) / len(away_probs),
    }


def add_candidate(rows, match_name, market, side, fair_prob, best):
    if fair_prob is None or best is None:
        return

    edge = fair_prob - best["implied_prob"]

    rows.append({
        "match": match_name,
        "league": LEAGUE_LABEL,
        "market": market,
        "side": side,
        "kalshi_price": "-",
        "true_prob": round(fair_prob * 100, 1),
        "book_prob": round(best["implied_prob"] * 100, 1),
        "edge": round(edge * 100, 1),
        "signal": classify_edge(edge),
        "books": best["book"],
        "notes": f"Best price {best['price']}"
    })


def scan_btts():
    if not ODDS_API_KEY:
        return [{
            "match": "Missing ODDS_API_KEY",
            "league": "-",
            "market": "-",
            "side": "-",
            "kalshi_price": "-",
            "true_prob": "-",
            "book_prob": "-",
            "edge": "-",
            "signal": "CHECK ENV",
            "books": "",
            "notes": ""
        }]

    events = get_league_odds()
    rows = []

    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        match_name = f"{home} vs {away}"
        bookmakers = event.get("bookmakers", [])

        if not bookmakers:
            continue

        btts = consensus_btts(bookmakers)
        if btts:
            add_candidate(rows, match_name, "BTTS", "YES", btts["yes"], best_price_for_outcome(bookmakers, "btts", "yes"))
            add_candidate(rows, match_name, "BTTS", "NO", btts["no"], best_price_for_outcome(bookmakers, "btts", "no"))

        totals = consensus_totals_25(bookmakers)
        if totals:
            add_candidate(rows, match_name, "TOTALS 2.5", "OVER", totals["over"], best_price_for_outcome(bookmakers, "totals", "over", point=2.5))
            add_candidate(rows, match_name, "TOTALS 2.5", "UNDER", totals["under"], best_price_for_outcome(bookmakers, "totals", "under", point=2.5))

        ml = consensus_moneyline(bookmakers, home, away)
        if ml:
            add_candidate(rows, match_name, "MONEYLINE", "HOME", ml["home"], best_price_for_outcome(bookmakers, "h2h", home))
            add_candidate(rows, match_name, "MONEYLINE", "DRAW", ml["draw"], best_price_for_outcome(bookmakers, "h2h", "draw"))
            add_candidate(rows, match_name, "MONEYLINE", "AWAY", ml["away"], best_price_for_outcome(bookmakers, "h2h", away))

    if not rows:
        return [{
            "match": "No usable MLS markets found",
            "league": LEAGUE_LABEL,
            "market": "-",
            "side": "-",
            "kalshi_price": "-",
            "true_prob": "-",
            "book_prob": "-",
            "edge": "-",
            "signal": "NO DATA",
            "books": "",
            "notes": ""
        }]

    # Best bet per match
    rank = {"BET": 3, "WATCH": 2, "PASS": 1, "NO DATA": 0}
    best_by_match = {}

    for row in rows:
        key = row["match"]
        current = best_by_match.get(key)

        if current is None:
            best_by_match[key] = row
            continue

        row_rank = rank.get(row["signal"], 0)
        cur_rank = rank.get(current["signal"], 0)

        row_edge = row["edge"] if isinstance(row["edge"], (int, float)) else -999
        cur_edge = current["edge"] if isinstance(current["edge"], (int, float)) else -999

        if row_rank > cur_rank or (row_rank == cur_rank and row_edge > cur_edge):
            best_by_match[key] = row

    final_rows = list(best_by_match.values())
    final_rows.sort(key=lambda x: (rank.get(x["signal"], 0), x["edge"] if isinstance(x["edge"], (int, float)) else -999), reverse=True)

    return final_rows
