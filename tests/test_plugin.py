import json
from pathlib import Path

from fastapi.testclient import TestClient

import db
import etl
import scoring
from app import app
from mock_vibecheck import CAPTIONS
from tone import EngagementModel, TeamTone

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((ROOT / "sample.json").read_text())
client = TestClient(app)


def mock_posts():
    return [etl.clean_post({"id": i, "caption": c, "likes": l, "label": "team"})
            for i, (c, l) in enumerate(CAPTIONS)]


# ---------- ETL ----------
def test_clean_caption_splits_hashtags_and_emojis():
    c = etl.clean_caption("The wait is over! 🚀 Link in bio. #Techkriti #Hackathon")
    assert c["hashtags"] == ["techkriti", "hackathon"]
    assert c["emojis"] == ["🚀"]
    assert "#" not in c["clean_text"] and "🚀" not in c["clean_text"]
    assert c["has_exclaim"] and not c["has_question"]


def test_keywords_drop_stopwords_and_design_words():
    kw = etl.extract_keywords("light grey background, bold navy title, speaker cut-out on a blue square")
    assert "speaker" in kw["topic"]
    assert not {"background", "navy", "title", "the", "on"} & set(kw["topic"])


def test_mood_words_follow_style_features():
    assert "bold" in etl.mood_words({"contrast": 0.9})
    assert "dark and dramatic" in etl.mood_words({"brightness": 0.1})
    assert etl.mood_words({}) == ["balanced"]


def test_clean_post_skips_other_pages_and_empty_captions():
    assert etl.clean_post({"id": 1, "caption": "hi", "label": "other"}) is None
    assert etl.clean_post({"id": 1, "caption": "", "label": "team"}) is None


# ---------- AIML ----------
def test_tone_match_prefers_team_like_captions():
    tone = TeamTone(mock_posts())
    on_brand = "Meet our next speaker live at the Lecture Hall Complex! #Techkriti #TechTalks"
    off_brand = "quarterly invoice reconciliation procedures memo attached regards accounting"
    assert tone.tone_match(on_brand) > tone.tone_match(off_brand) + 20
    assert 0 <= tone.tone_match(off_brand) <= 100


def test_engagement_model_trains_and_predicts():
    posts = mock_posts()
    model = EngagementModel(posts, TeamTone(posts))
    assert model.ready
    assert model.predict_likes("Robowars is back! 🤖 #Techkriti") > 0


def test_engagement_model_needs_enough_data():
    posts = mock_posts()[:3]
    assert EngagementModel(posts, TeamTone(posts)).predict_likes("x") is None


def test_keyword_hits():
    assert scoring.keyword_hits("Meet our speakers tonight", ["speaker"]) == 1
    assert scoring.keyword_hits("Meet us tonight", ["speaker"]) == 0


# ---------- API / Panel ----------
def assert_valid_panel(p):
    assert isinstance(p["title"], str) and p["title"]
    for m in p.get("metrics") or []:
        assert "label" in m and isinstance(m["value"], (int, float, str))
    for it in p.get("items") or []:
        assert isinstance(it["text"], str) and it.get("ok") in (True, False, None)
    if p.get("chart"):
        assert p["chart"]["type"] in ("bar", "line")
        assert all(isinstance(pt["value"], (int, float)) for pt in p["chart"]["points"])


def test_hook_returns_valid_panel_with_fallback_generator():
    r = client.post("/hook", json=SAMPLE)
    assert r.status_code == 200
    p = r.json()
    assert_valid_panel(p)
    assert len(p["chart"]["points"]) == 4
    assert p["items"][0]["ok"] is True          # best caption is ticked
    assert "templates" in p["summary"]


def test_hook_learns_from_stored_posts():
    db.upsert_posts(SAMPLE["team"]["id"], mock_posts())
    p = client.post("/hook", json=SAMPLE).json()
    learned = next(m for m in p["metrics"] if m["label"] == "Captions learned from")
    assert learned["value"] >= 20
    assert any(m["label"].startswith("Predicted likes") for m in p["metrics"])


def test_other_events_get_a_message_panel():
    p = client.post("/hook", json={"event": "profile.viewed", "team": {"id": 1}}).json()
    assert_valid_panel(p)
    assert "items" not in p


def test_missing_team_is_handled():
    p = client.post("/hook", json={"event": "check.completed", "check": {}}).json()
    assert p["title"] == "Caption Suggester"
