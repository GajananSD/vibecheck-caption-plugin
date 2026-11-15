"""Caption Suggester - a VibeCheck cross-dev plugin.

VibeCheck POSTs a `check.completed` event to /hook after every check and
draws the Panel JSON we return inside its Result page.

Flow per check (must finish in < 5 s):
  1. ETL      - store the `nearest` captions, load the team's posts from SQLite,
                extract keywords + mood from the payload.
  2. AIML     - rebuild the team's tone profile + engagement model, generate
                captions (Gemini, template fallback), score and rank them.
  3. VIZ      - return a Panel (items, metrics, bar chart).
  The team's full post history is pulled from VibeCheck's API in the background
  after the response, so later checks learn from more data.

Run:  uvicorn app:app --port 8100 --reload
"""
import logging
import time

import httpx
from fastapi import BackgroundTasks, FastAPI

import config
import db
import etl
import generator
import panel
import scoring
from tone import EngagementModel, TeamTone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("caption")

app = FastAPI(
    title="Caption Suggester (VibeCheck plugin)",
    version="0.2.0",
    description="Suggests on-brand Instagram captions for a poster idea, "
                "learned from the team's past captions.",
)
db.init()
generator.warm_up()


def sync_team_posts(api_base: str, team_id: int):
    """Background ETL: pull every team post from VibeCheck and upsert into SQLite."""
    if not config.FETCH_POSTS or not api_base:
        return
    if time.time() - db.last_fetched(team_id) < config.POSTS_REFRESH_S:
        return
    rows, offset = [], 0
    try:
        with httpx.Client(base_url=api_base.rstrip("/"), timeout=10) as client:
            while True:
                r = client.get(f"/teams/{team_id}/posts",
                               params={"label": "team", "limit": 500, "offset": offset})
                r.raise_for_status()
                data = r.json()
                items = data.get("items", [])
                rows += [row for row in map(etl.clean_post, items) if row]
                offset += len(items)
                if not items or offset >= data.get("total", 0):
                    break
    except Exception as e:
        log.warning("Could not fetch posts for team %s from %s: %s", team_id, api_base, e)
        return
    db.upsert_posts(team_id, rows)
    db.mark_fetched(team_id, len(rows))
    log.info("Synced %d captioned posts for team %s", len(rows), team_id)


@app.get("/health")
def health():
    return {"ok": True, "gemini": config.USE_GEMINI, "model": config.GEMINI_MODEL}


@app.post("/hook")
def hook(event: dict, background: BackgroundTasks):
    """Receive a VibeCheck event and return a Panel."""
    t0 = time.perf_counter()
    if event.get("event") != "check.completed":
        return panel.message_panel("Caption ideas appear on each check's result page.")

    team = event.get("team") or {}
    check = event.get("check") or {}
    team_id = team.get("id")
    if team_id is None:
        return panel.message_panel("No team in the request, so no captions.")

    # 1. ETL
    nearest_rows = [r for r in map(etl.clean_post, check.get("nearest") or []) if r]
    if nearest_rows:
        db.upsert_posts(team_id, nearest_rows)
    posts = db.team_posts(team_id)
    inp = etl.build_input(event, posts)

    # 2. AIML
    tone = TeamTone(posts)
    model = EngagementModel(posts, tone)
    captions, source = generator.generate(inp, tone)
    scored = scoring.score_captions(captions, inp, tone, model)

    # 3. VIZ
    result = panel.build_panel(inp, scored, tone, model, source)

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    db.log_check(inp["check_id"], team_id, inp["description"], inp["vibe_score"],
                 inp["keywords"], inp["mood"], source, elapsed_ms, scored)
    api_base = config.VIBECHECK_API_BASE or event.get("api_base", "")
    background.add_task(sync_team_posts, api_base, team_id)
    log.info("check %s team %s: %d captions via %s in %d ms",
             inp["check_id"], team_id, len(scored), source, elapsed_ms)
    return result
