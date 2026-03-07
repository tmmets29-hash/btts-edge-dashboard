import csv
import os
import math
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import requests

ODDS_API_BASE = 'https://api.the-odds-api.com/v4'
KALSHI_BASE = 'https://api.elections.kalshi.com/trade-api/v2'
DEFAULT_LEAGUES = [
    'soccer_epl',
    'soccer_uefa_champs_league',
    'soccer_spain_la_liga',
    'soccer_italy_serie_a',
    'soccer_germany_bundesliga',
    'soccer_france_ligue_one',
]
USER_AGENT = 'BTTS-Edge-Dashboard/1.0'


def american_to_prob(price: float) -> float:
    if price > 0:
        return 100.0 / (price + 100.0)
    return abs(price) / (abs(price) + 100.0)


def devig_two_way(prob_a: float, prob_b: float) -> Tuple[float, float]:
    total = prob_a + prob_b
    if total == 0:
        return 0.0, 0.0
    return prob_a / total, prob_b / total


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def kelly_binary(p: float, price_cents: float) -> float:
    c = price_cents / 100.0
    if c <= 0 or c >= 1:
        return 0.0
    b = (1.0 - c) / c
    q = 1.0 - p
    raw = (b * p - q) / b
    return max(0.0, raw)


def load_config() -> Dict[str, str]:
    config = {
        'ODDS_API_KEY': os.getenv('ODDS_API_KEY', '').strip(),
        'EDGE_THRESHOLD_PCT': os.getenv('EDGE_THRESHOLD_PCT', '3'),
        'BANKROLL': os.getenv('BANKROLL', '1000'),
        'KELLY_FRACTION': os.getenv('KELLY_FRACTION', '0.25'),
        'BOOKMAKERS': os.getenv('BOOKMAKERS', ''),
    }
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in config and not config[k]:
                    config[k] = v
    return config


def _req(url: str, params: Optional[dict] = None) -> dict:
    r = requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_odds_events(api_key: str, leagues: List[str], bookmakers: Optional[str] = None) -> List[dict]:
    all_events = []
    for league in leagues:
        params = {
            'apiKey': api_key,
            'regions': 'us',
            'markets': 'btts',
            'oddsFormat': 'american',
        }
        if bookmakers:
            params['bookmakers'] = bookmakers
        url = f'{ODDS_API_BASE}/sports/{league}/odds/'
        try:
            data = _req(url, params)
            for event in data:
                event['sport_key'] = league
                all_events.append(event)
        except Exception:
            continue
    return all_events


def fetch_kalshi_markets(tickers: List[str]) -> List[dict]:
    rows = []
    for ticker in tickers:
        try:
            data = _req(f'{KALSHI_BASE}/markets/{ticker}')
            market = data.get('market', {})
            rows.append(market)
            time.sleep(0.05)
        except Exception:
            rows.append({'ticker': ticker, 'error': 'fetch_failed'})
    return rows


def load_market_map(path: Optional[str] = None) -> List[dict]:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'data', 'kalshi_markets.csv')
    rows = []
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get('enabled', 'Y')).upper() == 'Y':
                rows.append(row)
    return rows


def normalize_name(s: str) -> str:
    return ''.join(ch.lower() for ch in s if ch.isalnum() or ch.isspace()).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def choose_best_book_prob(event: dict) -> Optional[dict]:
    picks = []
    for book in event.get('bookmakers', []):
        for market in book.get('markets', []):
            if market.get('key') != 'btts':
                continue
            yes = no = None
            for outcome in market.get('outcomes', []):
                name = str(outcome.get('name', '')).lower()
                if name in ('yes', 'both teams to score - yes', 'btts yes'):
                    yes = float(outcome['price'])
                elif name in ('no', 'both teams to score - no', 'btts no'):
                    no = float(outcome['price'])
            if yes is not None and no is not None:
                p_yes, p_no = devig_two_way(american_to_prob(yes), american_to_prob(no))
                picks.append({
                    'book': book.get('title', book.get('key', 'Book')),
                    'yes_prob': p_yes,
                    'no_prob': p_no,
                    'yes_odds': yes,
                    'no_odds': no,
                    'updated': book.get('last_update')
                })
    if not picks:
        return None
    avg_yes = sum(x['yes_prob'] for x in picks) / len(picks)
    avg_no = sum(x['no_prob'] for x in picks) / len(picks)
    return {
        'consensus_yes_prob': avg_yes,
        'consensus_no_prob': avg_no,
        'sample_size': len(picks),
        'books': picks,
    }


def scan_btts(leagues: Optional[List[str]] = None) -> dict:
    config = load_config()
    api_key = config['ODDS_API_KEY']
    if not api_key:
        raise RuntimeError('Missing ODDS_API_KEY. Put it in .env or your environment variables.')

    edge_threshold = float(config['EDGE_THRESHOLD_PCT']) / 100.0
    bankroll = float(config['BANKROLL'])
    kelly_fraction = float(config['KELLY_FRACTION'])
    bookmakers = config['BOOKMAKERS'] or None

    market_map = load_market_map()
    if leagues:
        leagues = [x for x in leagues if x]
    else:
        leagues = sorted({row['sport_key'] for row in market_map if row.get('sport_key')}) or DEFAULT_LEAGUES

    odds_events = fetch_odds_events(api_key, leagues, bookmakers)
    kalshi = {m.get('ticker'): m for m in fetch_kalshi_markets([row['kalshi_ticker'] for row in market_map])}

    rows = []
    for row in market_map:
        match_name = row['match_name']
        league = row['sport_key']
        ticker = row['kalshi_ticker']
        preferred_side = str(row.get('preferred_side', 'AUTO')).upper()

        candidates = []
        for event in odds_events:
            if event.get('sport_key') != league:
                continue
            event_name = f"{event.get('away_team', '')} vs {event.get('home_team', '')}".strip()
            score = max(
                similarity(match_name, event_name),
                similarity(match_name, f"{event.get('home_team', '')} vs {event.get('away_team', '')}"),
                similarity(match_name, f"{event.get('home_team', '')} v {event.get('away_team', '')}"),
            )
            candidates.append((score, event))
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, event = candidates[0] if candidates else (0, None)
        book = choose_best_book_prob(event) if event else None
        market = kalshi.get(ticker, {})

        yes_price = market.get('yes_ask')
        no_price = market.get('no_ask')
        if yes_price is None and market.get('yes_ask_dollars') is not None:
            yes_price = round(float(market['yes_ask_dollars']) * 100)
        if no_price is None and market.get('no_ask_dollars') is not None:
            no_price = round(float(market['no_ask_dollars']) * 100)

        yes_prob = (yes_price / 100.0) if isinstance(yes_price, (int, float)) else None
        no_prob = (no_price / 100.0) if isinstance(no_price, (int, float)) else None

        consensus_yes = book['consensus_yes_prob'] if book else None
        consensus_no = book['consensus_no_prob'] if book else None

        edge_yes = (consensus_yes - yes_prob) if (consensus_yes is not None and yes_prob is not None) else None
        edge_no = (consensus_no - no_prob) if (consensus_no is not None and no_prob is not None) else None

        if preferred_side == 'YES':
            best_side = 'YES'
        elif preferred_side == 'NO':
            best_side = 'NO'
        else:
            cand_yes = edge_yes if edge_yes is not None else -999
            cand_no = edge_no if edge_no is not None else -999
            best_side = 'YES' if cand_yes >= cand_no else 'NO'

        edge = edge_yes if best_side == 'YES' else edge_no
        kalshi_price = yes_price if best_side == 'YES' else no_price
        true_prob = consensus_yes if best_side == 'YES' else consensus_no
        kelly_pct = kelly_binary(true_prob or 0, kalshi_price or 0) * kelly_fraction if (true_prob is not None and kalshi_price is not None) else 0.0
        stake = bankroll * kelly_pct
        signal = 'BET' if (edge is not None and edge >= edge_threshold) else 'PASS'
        notes = []
        if best_score < 0.78:
            notes.append('Review match')
        if not book:
            notes.append('No book odds')
        if yes_price is None or no_price is None:
            notes.append('Kalshi quote missing')
        if market.get('status') and market.get('status') != 'open':
            notes.append(f"Kalshi {market.get('status')}")

        rows.append({
            'match': match_name,
            'league': league,
            'kalshi_ticker': ticker,
            'kalshi_title': market.get('title', ''),
            'match_score': round(best_score, 3),
            'book_event': f"{event.get('away_team')} vs {event.get('home_team')}" if event else '',
            'consensus_yes_prob': round(consensus_yes, 4) if consensus_yes is not None else None,
            'consensus_no_prob': round(consensus_no, 4) if consensus_no is not None else None,
            'kalshi_yes_price': yes_price,
            'kalshi_no_price': no_price,
            'edge_yes': round(edge_yes, 4) if edge_yes is not None else None,
            'edge_no': round(edge_no, 4) if edge_no is not None else None,
            'best_side': best_side,
            'best_edge': round(edge, 4) if edge is not None else None,
            'true_prob': round(true_prob, 4) if true_prob is not None else None,
            'signal': signal,
            'kelly_pct': round(kelly_pct, 4),
            'stake': round(stake, 2),
            'book_count': book['sample_size'] if book else 0,
            'top_book': book['books'][0]['book'] if book and book['books'] else '',
            'notes': '; '.join(notes),
        })

    rows.sort(key=lambda x: ((x['best_edge'] is not None), x['best_edge'] or -999), reverse=True)
    return {
        'ok': True,
        'generated_at': int(time.time()),
        'rows': rows,
        'config': {
            'edge_threshold_pct': edge_threshold * 100,
            'bankroll': bankroll,
            'kelly_fraction': kelly_fraction,
            'leagues': leagues,
        }
    }
