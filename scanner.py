import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

LEAGUES = [
    {"sport_key": "soccer_usa_mls", "label": "MLS"},
    {"sport_key": "soccer_epl", "label": "EPL"},
    {"sport_key": "soccer_spain_la_liga", "label": "La Liga"},
    {"sport_key": "soccer_italy_serie_a", "label": "Serie A"},
    {"sport_key": "soccer_germany_bundesliga", "label": "Bundesliga"},
    {"sport_key": "soccer_france_ligue_one", "label": "Ligue 1"},
]

SHARP_BOOKS = ["Pinnacle", "bet365", "Bet365"]


def odds_to_prob(price):
    try:
        price = float(price)
        if price <= 1:
            return None
        return 1 / price
    except Exception:
        return None


def prob_to_implied_price(prob):
    try:
        prob = float(prob)
        if prob <= 0:
            return None
        return round(100 * prob, 1)
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


def get_events_for_league(sport_key):
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events"
        r = requests.get(url, params={"apiKey": ODDS_API_KEY}, timeout=20)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def get_event_odds(sport_key, event_id):
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "markets": "btts,totals,h2h",
            "regions": "us,uk,eu",
            "oddsFormat": "decimal"
        }
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def choose_sharp_two_way(bookmakers, market_key, side_a_name, side_b_name, point=None):
    sharp_rows = []

    for book in bookmakers:
        if book.get("title") not in SHARP_BOOKS:
            continue

        for market in book.get("markets", []):
            if market.get("key") != market_key:
                continue

            if point is not None:
                market_point = market.get("point")
                if market_point is None or float(market_point) != float(point):
                    continue

            a_price = None
            b_price = None

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).lower()
                price = outcome.get("price")

                if name == side_a_name.lower():
                    a_price = price
                elif name == side_b_name.lower():
                    b_price = price

            if a_price is None or b_price is None:
                continue

            pa = odds_to_prob(a_price)
            pb = odds_to_prob(b_price)

            if pa is None or pb is None:
                continue

            fa, fb = devig_two_way(pa, pb)
            if fa is None or fb is None:
                continue

            sharp_rows.append({
                "book": book.get("title", ""),
                "a_price": float(a_price),
                "b_price": float(b_price),
                "a_fair": fa,
                "b_fair": fb
            })

    if not sharp_rows:
        return None

    # prefer the sharpest consensus-ish row by averaging fair probs
    avg_a = sum(r["a_fair"] for r in sharp_rows) / len(sharp_rows)
    avg_b = sum(r["b_fair"] for r in sharp_rows) / len(sharp_rows)

    return {
        "fair_a": avg_a,
        "fair_b": avg_b,
        "books": ", ".join(sorted(set(r["book"] for r in sharp_rows)))
    }


def choose_sharp_three_way(bookmakers, home_team, away_team):
    sharp_rows = []

    for book in bookmakers:
        if book.get("title") not in SHARP_BOOKS:
            continue

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

            sharp_rows.append({
                "book": book.get("title", ""),
                "home_fair": fh,
                "draw_fair": fd,
                "away_fair": fa
            })

    if not sharp_rows:
        return None

    avg_home = sum(r["home_fair"] for r in sharp_rows) / len(sharp_rows)
    avg_draw = sum(r["draw_fair"] for r in sharp_rows) / len(sharp_rows)
    avg_away = sum(r["away_fair"] for r in sharp_rows) / len(sharp_rows)

    return {
        "fair_home": avg_home,
        "fair_draw": avg_draw,
        "fair_away": avg_away,
        "books": ", ".join(sorted(set(r["book"] for r in sharp_rows)))
    }


def best_outlier_two_way(bookmakers, market_key, side_name, point=None):
    best_price = None
    best_book = ""

    for book in bookmakers:
        for market in book.get("markets", []):
            if market.get("key") != market_key:
                continue

            if point is not None:
                market_point = market.get("point")
                if market_point is None or float(market_point) != float(point):
                    continue

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).lower()
                price = outcome.get("price")

                if name != side_name.lower():
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
        "book": best_book,
        "price": best_price,
        "implied_prob": implied
    }


def best_outlier_moneyline(bookmakers, side_name):
    best_price = None
    best_book = ""

    for book in bookmakers:
        for market in book.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):
                name = str(outcome.get("name", "")).strip()
                price = outcome.get("price")

                if name != side_name:
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
        "book": best_book,
        "price": best_price,
        "implied_prob": implied
    }


def classify_edge(edge):
    if edge is None:
        return "NO DATA"
    if edge >= 0.07:
        return "OBVIOUS BET"
    if edge >= 0.04:
        return "BET"
    if edge >= 0.02:
        return "WATCH"
    return "PASS"


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

    rows = []

    for league in LEAGUES:
        events = get_events_for_league(league["sport_key"])

        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            match_name = f"{home} vs {away}"

            odds = get_event_odds(league["sport_key"], event.get("id"))
            if not odds:
                continue

            bookmakers = odds.get("bookmakers", [])

            # ---------------------------
            # BTTS
            # ---------------------------
            sharp_btts = choose_sharp_two_way(bookmakers, "btts", "yes", "no")
            if sharp_btts:
                for side, fair_prob in [("YES", sharp_btts["fair_a"]), ("NO", sharp_btts["fair_b"])]:
                    outlier = best_outlier_two_way(bookmakers, "btts", "yes" if side == "YES" else "no")
                    if not outlier:
                        continue

                    edge = fair_prob - outlier["implied_prob"]
                    rows.append({
                        "match": match_name,
                        "league": league["label"],
                        "market": "BTTS",
                        "side": side,
                        "kalshi_price": "-",
                        "true_prob": round(fair_prob * 100, 1),
                        "book_prob": round(outlier["implied_prob"] * 100, 1),
                        "edge": round(edge * 100, 1),
                        "signal": classify_edge(edge),
                        "books": f"Sharp: {sharp_btts['books']} | Best: {outlier['book']}",
                        "notes": f"Best price {outlier['price']}"
                    })

            # ---------------------------
            # TOTALS 2.5
            # ---------------------------
            sharp_totals = choose_sharp_two_way(bookmakers, "totals", "over", "under", point=2.5)
            if sharp_totals:
                for side, fair_prob in [("OVER", sharp_totals["fair_a"]), ("UNDER", sharp_totals["fair_b"])]:
                    outlier = best_outlier_two_way(bookmakers, "totals", "over" if side == "OVER" else "under", point=2.5)
                    if not outlier:
                        continue

                    edge = fair_prob - outlier["implied_prob"]
                    rows.append({
                        "match": match_name,
                        "league": league["label"],
                        "market": "TOTALS 2.5",
                        "side": side,
                        "kalshi_price": "-",
                        "true_prob": round(fair_prob * 100, 1),
                        "book_prob": round(outlier["implied_prob"] * 100, 1),
                        "edge": round(edge * 100, 1),
                        "signal": classify_edge(edge),
                        "books": f"Sharp: {sharp_totals['books']} | Best: {outlier['book']}",
                        "notes": f"Best price {outlier['price']}"
                    })

            # ---------------------------
            # MONEYLINE
            # ---------------------------
            sharp_ml = choose_sharp_three_way(bookmakers, home, away)
            if sharp_ml:
                ml_sides = [
                    ("HOME", home, sharp_ml["fair_home"]),
                    ("DRAW", "Draw", sharp_ml["fair_draw"]),
                    ("AWAY", away, sharp_ml["fair_away"])
                ]

                for side_label, outcome_name, fair_prob in ml_sides:
                    outlier = best_outlier_moneyline(bookmakers, outcome_name)
                    if not outlier:
                        continue

                    edge = fair_prob - outlier["implied_prob"]
                    rows.append({
                        "match": match_name,
                        "league": league["label"],
                        "market": "MONEYLINE",
                        "side": side_label,
                        "kalshi_price": "-",
                        "true_prob": round(fair_prob * 100, 1),
                        "book_prob": round(outlier["implied_prob"] * 100, 1),
                        "edge": round(edge * 100, 1),
                        "signal": classify_edge(edge),
                        "books": f"Sharp: {sharp_ml['books']} | Best: {outlier['book']}",
                        "notes": f"Best price {outlier['price']}"
                    })

    if not rows:
        return [{
            "match": "No usable markets found",
            "league": "-",
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

    # keep only best bet per match
    best_by_match = {}

    signal_rank = {
        "OBVIOUS BET": 4,
        "BET": 3,
        "WATCH": 2,
        "PASS": 1,
        "NO DATA": 0
    }

    for row in rows:
        key = row["match"]
        current = best_by_match.get(key)

        row_rank = signal_rank.get(row["signal"], 0)
        row_edge = row["edge"] if isinstance(row["edge"], (int, float)) else -999

        if current is None:
            best_by_match[key] = row
            continue

        current_rank = signal_rank.get(current["signal"], 0)
        current_edge = current["edge"] if isinstance(current["edge"], (int, float)) else -999

        if row_rank > current_rank or (row_rank == current_rank and row_edge > current_edge):
            best_by_match[key] = row

    final_rows = list(best_by_match.values())
    final_rows.sort(key=lambda x: (
        signal_rank.get(x["signal"], 0),
        x["edge"] if isinstance(x["edge"], (int, float)) else -999
    ), reverse=True)

    return final_rows
