"""ETL: turn VibeCheck's payload + the team's past posts into structured model input."""
import re

STOPWORDS = set("""
a an the and or but if then so of to in on at by for with from into onto over under
up down out off is are was were be been being am do does did have has had this that
these those it its it's i me my we our you your they them their he she his her as
not no yes can will just than too very also about all any some more most such only
own same other each few both here there when where why how what which who whom
s t don should now let lets get got via per amp rt
""".split())

# Words that describe the poster's *look*, not its subject. They are kept for
# mood but left out of the "topic" keywords a caption should mention.
DESIGN_WORDS = set("""
background backdrop title subtitle heading headline text font fonts typeface typography
serif sans bold italic layout grid colour color colours colors palette gradient
light dark bright pale deep neon pastel grey gray black white red blue green yellow
orange purple pink navy teal cyan magenta brown gold silver beige cream maroon
square circle box shape shapes border frame cut-out cutout overlay texture pattern
left right top bottom center centre corner big small large tiny minimal clean
photo photograph image picture illustration illustrated graphic graphics icon icons
poster design style look vibe aesthetic theme retro vintage modern flat glossy
matte blur blurred shadow glow outline stroke logo
""".split())

EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF]{2}"          # flags
    "|[\U0001F300-\U0001FAFF]"           # pictographs, emoticons, symbols
    "|[☀-➿]"                    # misc symbols, dingbats
)
HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@([\w.]+)")
URL_RE = re.compile(r"https?://\S+")
WORD_RE = re.compile(r"[a-z][a-z'\-]*[a-z]|[a-z]")


def tokenize(text: str) -> list[str]:
    """Lower-case content words, without hashtags, mentions, URLs and stopwords."""
    text = URL_RE.sub(" ", text or "")
    text = HASHTAG_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    words = WORD_RE.findall(text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def clean_caption(caption: str) -> dict:
    caption = caption or ""
    text = URL_RE.sub(" ", caption)
    text = HASHTAG_RE.sub(" ", text)
    text = MENTION_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "caption": caption,
        "clean_text": text,
        "hashtags": [h.lower() for h in HASHTAG_RE.findall(caption)],
        "emojis": EMOJI_RE.findall(caption),
        "n_words": len(text.split()),
        "has_question": "?" in caption,
        "has_exclaim": "!" in caption,
        "n_lines": caption.count("\n") + 1,
    }


def clean_post(post: dict) -> dict | None:
    """A VibeCheck post (from `nearest` or /posts) -> row for the posts table."""
    if not post.get("caption") or post.get("id") is None:
        return None
    if post.get("label", "team") != "team":   # only learn the team's own voice
        return None
    row = clean_caption(post["caption"])
    row.update(post_id=int(post["id"]), likes=post.get("likes"),
               comments=post.get("comments"), posted_at=post.get("posted_at"))
    return row


def extract_keywords(description: str, max_n: int = 8) -> dict:
    """Ordered unique keywords; `topic` drops design-vocabulary words."""
    seen, ordered = set(), []
    for w in tokenize(description):
        if w not in seen:
            seen.add(w)
            ordered.append(w)
    topic = [w for w in ordered if w not in DESIGN_WORDS]
    return {"all": ordered[:max_n], "topic": topic[:max_n]}


def mood_words(style: dict) -> list[str]:
    """Map VibeCheck's 0-1 style features to tone words for the caption."""
    s = style or {}

    def g(k):  # missing feature -> neutral value that triggers no rule
        v = s.get(k)
        return 0.4 if v is None else float(v)

    rules = [
        (g("contrast") > 0.7, "bold"),
        (g("contrast") < 0.3, "soft"),
        (g("saturation") > 0.6, "vibrant"),
        (g("saturation") < 0.25, "understated"),
        (g("warmth") > 0.6, "warm and energetic"),
        (g("warmth") < 0.35, "cool and composed"),
        (g("brightness") > 0.7, "bright and upbeat"),
        (g("brightness") < 0.3, "dark and dramatic"),
        (g("whitespace") > 0.45, "clean and minimal"),
        (g("busyness") > 0.65, "lively"),
        (g("illustration") > 0.6, "playful"),
        (g("illustration") < 0.3, "real and grounded"),
        (g("text_amount") > 0.7, "informative"),
    ]
    words = [w for cond, w in rules if cond]
    return words[:4] or ["balanced"]


def build_input(event: dict, posts: list[dict]) -> dict:
    """Everything the generator and scorer need, in one structured dict."""
    team = event.get("team") or {}
    check = event.get("check") or {}
    description = (check.get("description") or "").strip()
    kw = extract_keywords(description)
    best = sorted((p for p in posts if p.get("clean_text")),
                  key=lambda p: p.get("likes") or 0, reverse=True)
    return {
        "team_id": team.get("id"),
        "team_name": team.get("name") or "the team",
        "handle": team.get("instagram_handle") or "",
        "check_id": check.get("id"),
        "vibe_score": check.get("score"),
        "verdict": check.get("verdict"),
        "description": description,
        "keywords": kw["all"],
        "topic": kw["topic"] or kw["all"],
        "mood": mood_words(check.get("plan_style")),
        "palette": [c.get("hex") for c in check.get("plan_palette") or [] if isinstance(c, dict)],
        "examples": [p["caption"] for p in best[:3]],
    }
