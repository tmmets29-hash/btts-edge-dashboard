# BTTS Edge Radar Mobile

A mobile-first Flask dashboard that compares Kalshi BTTS prices with a de-vigged sportsbook consensus from The Odds API.

## Why this version

This one is built for phones first:
- chunky tap targets
- card layout on small screens
- simple deploy to Render
- no spreadsheet UI fighting you on iPhone

## What you need

- A The Odds API key
- A small `kalshi_markets.csv` mapping file with the fixtures and Kalshi tickers you want to watch
- A Render account if you want it hosted as a normal mobile website

## Local run

1. Copy `.env.example` to `.env`
2. Put your Odds API key in `.env`
3. Copy `kalshi_markets.example.csv` to `data/kalshi_markets.csv` or edit the existing CSV location in `scanner.py`
4. Run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5001`

## Render deploy

1. Create a new GitHub repo
2. Upload all files from this folder
3. In Render, choose **New Web Service**
4. Connect the repo
5. Render will detect `render.yaml`
6. Add your secret `ODDS_API_KEY`
7. Deploy

After deploy, open the Render URL on your phone and save it to your home screen.

## Files

- `app.py` web app
- `scanner.py` BTTS scan logic
- `templates/index.html` mobile-first UI
- `kalshi_markets.example.csv` starter ticker map
- `.env.example` config example
- `render.yaml` one-click-ish Render setup

## Notes

- Kalshi tickers still need to be maintained by you
- If you see `Review match`, the fuzzy event match was shaky and needs human eyeballs
- This is intentionally simple and not a full market-making model
