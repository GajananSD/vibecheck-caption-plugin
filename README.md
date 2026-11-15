# Caption Suggester — VibeCheck plugin

Cross-dev plugin for VibeCheck. After every check, VibeCheck POSTs the poster
data to `/hook`; we return a Panel with on-brand caption suggestions, metrics
and a chart, shown inside VibeCheck's Result page.

## How it works

| Component | File | What it does |
|---|---|---|
| ETL | `etl.py`, `db.py` | Cleans captions (hashtags, emojis, mentions), extracts subject keywords from the description, maps style features to mood words, stores team posts / checks / suggestions in SQLite (`captions.db`). The team's full post history is pulled from `GET {api_base}/teams/{id}/posts` in the background (at most every 30 min). |
| AIML | `tone.py`, `generator.py` | Per-team **tone profile** (TF-IDF vocabulary + length/emoji/hashtag habits) and a **ridge-regression likes model**, rebuilt from stored posts on every check. Captions come from **Gemini** (3 s timeout, cached, pauses on 429), with a template generator as the fallback. |
| Scoring | `scoring.py` | Tone match (0–100), keyword hits, predicted likes; combined fit score ranks the captions. |
| VIZ | `panel.py` | Panel: ranked captions (best ticked), metrics, bar chart of tone match per caption. |
| APP / DEV | `app.py` | FastAPI service, `POST /hook` (+ `GET /health`). Interactive docs at `/docs`. |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY
```

## Run

```bash
uvicorn app:app --host 0.0.0.0 --port 8100
```

## Test locally (no VibeCheck server needed)

```bash
uvicorn mock_vibecheck:app --port 8000      # fake /teams/1/posts with test captions
curl -s -X POST http://localhost:8100/hook -H "Content-Type: application/json" -d @sample.json
python -m pytest -q tests                    # unit tests (Gemini off)
```

The mock posts are stored in `captions.db`; delete that file before a real demo.

## Register with VibeCheck

```bash
curl -X POST $API/plugins -H "Content-Type: application/json" \
  -d '{"name": "Caption Suggester", "url": "http://<your-ip>:8100/hook", "slot": "result", "author_team": "<our team>"}'
```

## Notes

- Gemini free tier allows ~5 requests/minute per model. Repeated checks of the same
  idea are served from cache; when the quota is hit, the template generator answers.
- Settings (`.env`): `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_S`, `USE_GEMINI`,
  `FETCH_POSTS`, `POSTS_REFRESH_S`, `PLUGIN_DB_PATH`.
