import os
import re
import requests
from difflib import SequenceMatcher

ODDS_KEY = os.getenv("ODDS_API_KEY")

KALSHI_EVENTS_URL = "https://api.elections.kalshi.com/trade-api/v2/events"
ODDS_SPORTS = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
]

def normalize_team(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("fc ", "").replace(" fc", "")
    s = s.replace("cf ", "").replace(" cf", "")
    s = s.replace("ac ", "").replace(" ac", "")
    s = s.replace("afc ", "").replace(" afc", "")
    s = s.replace("sv ", "").replace(" sv", "")
    s = s.replace("1. ", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_kalshi_match(title: str):
    # Examples:
    # "Dortmund at FC Köln: Both Teams to Score"
    # "Hamburg vs Leipzig: Both Teams to Score"
    t = title.replace(": Both Teams to Score", "").strip()

    if " at " in t:
        away, home = t.split(" at ", 1)
        return normalize_team(home), normalize_team(away)

    if " vs " in t:
        home, away = t.split(" vs ", 1)
        return normalize_team(home), normalize_team(away)

    return None, None

def event_match_score(k_home: str, k_away: str, o_home: str, o_away: str) -> float:
    a = SequenceMatcher(None, k_home, o_home).ratio()
    b = SequenceMatcher(None, k_away, o_away).ratio()
    c = SequenceMatcher(None, k_home, o_away).ratio()
    d = SequenceMatcher(None, k_away, o_home).ratio()

    direct = (a + b) / 2
    swapped = (c + d) / 2
    return max(direct, swapped)

def devig_two_way(yes_price, no_price):
    yes_p = 1 / float(yes_price)
    no_p = 1 / float(no_price)
    overround = yes_p + no_p
    if overround <= 0:
        return None
    fair_yes = yes_p / overround
    fair_no = no_p / overround
    return fair_yes, fair_no

def get_kalshi_btts_markets():
    # Inference from Kalshi docs: requesting events with nested markets is the cleanest way
    # to get event + market price fields in one response.
    params = {
        "with_nested_markets": "true",
        "limit": 200
    }

    r = requests.get(KALSHI_EVENTS_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    results = []
    for event in data.get("events", []):
        for market in event.get("markets", []):
            title = market.get("title", "") or ""
            subtitle = market.get("subtitle", "") or ""

            title_blob = f"{event.get('title', '')} {title} {subtitle}".lower()

            if "both teams to score" not in title_blob and "btts" not in title_blob:
                continue

            home, away = split_kalshi_match(title or event.get("title", ""))
            if not home or not away:
                continue

            yes_ask = market.get("yes_ask_dollars")
            no_ask = market.get("no_ask_dollars")

            if yes_ask is None and no_ask is None:
                continue

            results.append({
                "kalshi_title": title or event.get("title", ""),
                "kalshi_ticker": market.get("ticker"),
                "home_norm": home,
                "away_norm": away,
                "yes_ask": float(yes_ask) if yes_ask is not None else None,
                "no_ask": float(no_ask) if no_ask is not None else None,
            })

    return results

def get_odds_events_for_sport(sport_key: str):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_KEY,
        "regions": "uk,eu,us",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        return []
    return r.json()

def get_btts_for_event(sport_key: str, event_id: str):
    # Per Odds API docs, btts is an additional soccer market fetched event-by-event.
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_KEY,
        "regions": "uk,eu,us",
        "markets": "btts",
        "oddsFormat": "decimal",
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        return None

    data = r.json()

    best_yes = None
    best_no = None
    books_used = []

    for book in data.get("bookmakers", []):
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

            if best_yes is None or float(yes_price) > float(best_yes):
                best_yes = float(yes_price)
            if best_no is None or float(no_price) > float(best_no):
                best_no = float(no_price)

            books_used.append(book.get("title", ""))

    if best_yes is None or best_no is None:
        return None

    fair = devig_two_way(best_yes, best_no)
    if fair is None:
        return None

    fair_yes, fair_no = fair
    return {
        "best_yes": best_yes,
        "best_no": best_no,
        "fair_yes": fair_yes,
        "fair_no": fair_no,
        "books": ", ".join(sorted(set([b for b in books_used if b])))
    }

def scan_btts():
    if not ODDS_KEY:
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

    odds_events_by_sport = {
        sport: get_odds_events_for_sport(sport)
        for sport in ODDS_SPORTS
    }

    rows = []

    for km in kalshi_markets:
        best_match = None
        best_sport = None
        best_score = 0.0

        for sport, events in odds_events_by_sport.items():
            for ev in events:
                o_home = normalize_team(ev.get("home_team", ""))
                o_away = normalize_team(ev.get("away_team", ""))

                score = event_match_score(km["home_norm"], km["away_norm"], o_home, o_away)
                if score > best_score:
                    best_score = score
                    best_match = ev
                    best_sport = sport

        if not best_match or best_score < 0.72:
            rows.append({
                "match": km["kalshi_title"],
                "kalshi_price": round((km["yes_ask"] or 0) * 100, 1) if km["yes_ask"] is not None else "-",
                "true_prob": "-",
                "edge": "-",
                "signal": "REVIEW",
                "books": "",
                "notes": f"No confident odds match, score={best_score:.2f}"
            })
            continue

        event_btts = get_btts_for_event(best_sport, best_match["id"])
        if not event_btts:
            rows.append({
                "match": km["kalshi_title"],
                "kalshi_price": round((km["yes_ask"] or 0) * 100, 1) if km["yes_ask"] is not None else "-",
                "true_prob": "-",
                "edge": "-",
                "signal": "NO BTTS",
                "books": "",
                "notes": f"Matched odds event, but no BTTS returned. score={best_score:.2f}"
            })
            continue

        if km["yes_ask"] is None:
            rows.append({
                "match": km["kalshi_title"],
                "kalshi_price": "-",
                "true_prob": round(event_btts["fair_yes"] * 100, 1),
                "edge": "-",
                "signal": "NO ASK",
                "books": event_btts["books"],
                "notes": f"score={best_score:.2f}"
            })
            continue

        edge = event_btts["fair_yes"] - km["yes_ask"]
        signal = "BET" if edge > 0.03 else "PASS"

        rows.append({
            "match": km["kalshi_title"],
            "kalshi_price": round(km["yes_ask"] * 100, 1),
            "true_prob": round(event_btts["fair_yes"] * 100, 1),
            "edge": round(edge * 100, 1),
            "signal": signal,
            "books": event_btts["books"],
            "notes": f"score={best_score:.2f} ticker={km['kalshi_ticker']}"
        })

    rows.sort(key=lambda x: (x["edge"] if isinstance(x["edge"], (int, float)) else -999), reverse=True)
    return rows[:50]
