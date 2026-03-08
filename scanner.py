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

SHARP_BOOKS = {
    "Pinnacle",
    "Pinnacle Sports",
    "Bet365",
    "bet365",
    "Betfair",
    "DraftKings",
    "FanDuel",
    "Caesars"
}


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


def eligible_books(bookmakers, sharp_only=True):
    if sharp_only:
        books = [b for b in bookmakers if b.get("title") in SHARP_BOOKS]
        if books:
            return books
    return bookmakers


def choose_two_way_fair(bookmakers, market_key, side_a_name, side_b_name, point=None):
    for sharp_only in [True, False]:
        rows = []

        for book in eligible_books(bookmakers, sharp_only=sharp_only):
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

                rows.append({
                    "book": book.get("title", ""),
                    "a_fair": fa,
                    "b_fair": fb
                })

        if rows:
            avg_a = sum(r["a_fair"] for r in rows) / len(rows)
            avg_b = sum(r["b_fair"] for r in rows) / len(rows)
            return {
                "fair_a": avg_a,
                "fair_b": avg_b,
                "books": ", ".join(sorted(set(r["book"] for r in rows))),
                "sharp_only": sharp_only
            }

    return None


def choose_three_way_fair(bookmakers, home_team, away_team):
    for sharp_only in [True, False]:
        rows = []

        for book in eligible_books(bookmakers, sharp_only=sharp_only):
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

                rows.append({
                    "book": book.get("title", ""),
                    "home_fair": fh,
                    "draw_fair": fd,
                    "away_fair": fa
                })

        if rows:
            avg_home = sum(r["home_fair"] for r in rows) / len(rows)
            avg_draw = sum(r["draw_fair"] for r in rows) / len(rows)
            avg_away = sum(r["away_fair"] for r in rows) / len(rows)
            return {
                "fair_home": avg_home,
                "fair_draw": avg_draw,
                "fair_away": avg_away,
                "books": ", ".join(sorted(set(r["book"] for r in rows))),
                "sharp_only": sharp_only
            }

    return None


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
            if not bookmakers:
                continue

            # BTTS
            fair_btts = choose_two_way_fair(bookmakers, "btts", "yes", "no")
            if fair_btts:
                for side, fair_prob, side_name in [
                    ("YES", fair_btts["fair_a"], "yes"),
                    ("NO", fair_btts["fair_b"], "no"),
                ]:
                    outlier = best_outlier_two_way(bookmakers, "btts", side_name)
                    if outlier:
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
                            "books": f"Fair: {fair_btts['books']} | Best: {outlier['book']}",
                            "notes": f"Best price {outlier['price']}"
                        })

            # Totals 2.5
            fair_totals = choose_two_way_fair(bookmakers, "totals", "over", "under", point=2.5)
            if fair_totals:
                for side, fair_prob, side_name in [
                    ("OVER", fair_totals["fair_a"], "over"),
                    ("UNDER", fair_totals["fair_b"], "under"),
                ]:
                    outlier = best_outlier_two_way(bookmakers, "totals", side_name, point=2.5)
                    if outlier:
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
                            "books": f"Fair: {fair_totals['books']} | Best: {outlier['book']}",
                            "notes": f"Best price {outlier['price']}"
                        })

            # Moneyline
            fair_ml = choose_three_way_fair(bookmakers, home, away)
            if fair_ml:
                for side_label, outcome_name, fair_prob in [
                    ("HOME", home, fair_ml["fair_home"]),
                    ("DRAW", "Draw", fair_ml["fair_draw"]),
                    ("AWAY", away, fair_ml["fair_away"]),
                ]:
                    outlier = best_outlier_moneyline(bookmakers, outcome_name)
                    if outlier:
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
                            "books": f"Fair: {fair_ml['books']} | Best: {outlier['book']}",
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
            "notes": "Try fewer leagues or broader books"
        }]

    best_by_match = {}
    signal_rank = {"OBVIOUS BET": 4, "BET": 3, "WATCH": 2, "PASS": 1, "NO DATA": 0}

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
    final_rows.sort(
        key=lambda x: (
            signal_rank.get(x["signal"], 0),
            x["edge"] if isinstance(x["edge"], (int, float)) else -999
        ),
        reverse=True
    )

    return final_rows
