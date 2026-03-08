import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")

LEAGUES = [
    {"sport_key": "soccer_usa_mls", "label": "MLS"},
    {"sport_key": "soccer_epl", "label": "EPL"},
    {"sport_key": "soccer_germany_bundesliga", "label": "Bundesliga"},
]


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


def classify_edge(edge):
    if edge is None:
        return "NO DATA"
    if edge >= 0.04:
        return "BET"
    if edge >= 0.02:
        return "WATCH"
    return "PASS"


def best_price_for_side(bookmakers, market_key, side_name, point=None):
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
                name = str(outcome.get("name", "")).strip().lower()
                if name != side_name.strip().lower():
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


def consensus_two_way(bookmakers, market_key, side_a_name, side_b_name, point=None):
    fair_a_list = []
    fair_b_list = []
    books_used = set()

    for book in bookmakers:
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
                name = str(outcome.get("name", "")).strip().lower()
                price = outcome.get("price")

                if name == side_a_name.strip().lower():
                    a_price = price
                elif name == side_b_name.strip().lower():
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

            fair_a_list.append(fa)
            fair_b_list.append(fb)
            books_used.add(book.get("title", ""))

    if not fair_a_list or not fair_b_list:
        return None

    return {
        "fair_a": sum(fair_a_list) / len(fair_a_list),
        "fair_b": sum(fair_b_list) / len(fair_b_list),
        "books": ", ".join(sorted(books_used))
    }


def consensus_three_way(bookmakers, home_team, away_team):
    fair_home_list = []
    fair_draw_list = []
    fair_away_list = []
    books_used = set()

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

            fair_home_list.append(fh)
            fair_draw_list.append(fd)
            fair_away_list.append(fa)
            books_used.add(book.get("title", ""))

    if not fair_home_list:
        return None

    return {
        "fair_home": sum(fair_home_list) / len(fair_home_list),
        "fair_draw": sum(fair_draw_list) / len(fair_draw_list),
        "fair_away": sum(fair_away_list) / len(fair_away_list),
        "books": ", ".join(sorted(books_used))
    }


def add_candidate(rows, match_name, league_label, market, side, fair_prob, outlier):
    if fair_prob is None or outlier is None:
        return

    edge = fair_prob - outlier["implied_prob"]

    rows.append({
        "match": match_name,
        "league": league_label,
        "market": market,
        "side": side,
        "kalshi_price": "-",
        "true_prob": round(fair_prob * 100, 1),
        "book_prob": round(outlier["implied_prob"] * 100, 1),
        "edge": round(edge * 100, 1),
        "signal": classify_edge(edge),
        "books": f"Consensus vs {outlier['book']}",
        "notes": f"Best price {outlier['price']}"
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
            fair_btts = consensus_two_way(bookmakers, "btts", "yes", "no")
            if fair_btts:
                add_candidate(
                    rows, match_name, league["label"], "BTTS", "YES",
                    fair_btts["fair_a"],
                    best_price_for_side(bookmakers, "btts", "yes")
                )
                add_candidate(
                    rows, match_name, league["label"], "BTTS", "NO",
                    fair_btts["fair_b"],
                    best_price_for_side(bookmakers, "btts", "no")
                )

            # Totals 2.5
            fair_totals = consensus_two_way(bookmakers, "totals", "over", "under", point=2.5)
            if fair_totals:
                add_candidate(
                    rows, match_name, league["label"], "TOTALS 2.5", "OVER",
                    fair_totals["fair_a"],
                    best_price_for_side(bookmakers, "totals", "over", point=2.5)
                )
                add_candidate(
                    rows, match_name, league["label"], "TOTALS 2.5", "UNDER",
                    fair_totals["fair_b"],
                    best_price_for_side(bookmakers, "totals", "under", point=2.5)
                )

            # Moneyline
            fair_ml = consensus_three_way(bookmakers, home, away)
            if fair_ml:
                add_candidate(
                    rows, match_name, league["label"], "MONEYLINE", "HOME",
                    fair_ml["fair_home"],
                    best_price_for_side(bookmakers, "h2h", home)
                )
                add_candidate(
                    rows, match_name, league["label"], "MONEYLINE", "DRAW",
                    fair_ml["fair_draw"],
                    best_price_for_side(bookmakers, "h2h", "draw")
                )
                add_candidate(
                    rows, match_name, league["label"], "MONEYLINE", "AWAY",
                    fair_ml["fair_away"],
                    best_price_for_side(bookmakers, "h2h", away)
                )

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
            "notes": "Free-tier fallback found nothing"
        }]

    # only best bet per match
    best_by_match = {}
    signal_rank = {"BET": 3, "WATCH": 2, "PASS": 1, "NO DATA": 0}

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
