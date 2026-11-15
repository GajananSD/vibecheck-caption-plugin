"""Caption generation: Gemini first, a template generator as the fallback."""
import json
import logging
import random
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import config

log = logging.getLogger("caption.generator")
_pool = ThreadPoolExecutor(max_workers=4)
_client = None
_client_lock = threading.Lock()
_cooldown_until = 0.0              # set after a 429 (free tier: 5 requests/minute)
_cache: OrderedDict = OrderedDict()  # same idea checked again -> no new Gemini call
CACHE_SIZE = 128


def _gemini_client():
    global _client
    with _client_lock:
        if _client is None:
            from google import genai
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
        return _client


def warm_up():
    """Import the SDK and build the client at startup (first use costs ~1-2 s)."""
    if config.USE_GEMINI:
        _pool.submit(_gemini_client)


def _cache_key(inp: dict, tone, n: int) -> tuple:
    return (inp.get("team_id"), inp["description"].lower(), tuple(inp["mood"]), tone.n, n)


def build_prompt(inp: dict, tone, n: int) -> str:
    examples = "\n".join(f"{i + 1}. {e}" for i, e in enumerate(inp["examples"])) or "(none yet)"
    emoji_habit = ("often uses emojis, e.g. " + " ".join(tone.top_emojis[:3])
                   if tone.emoji_rate >= 1 else
                   "uses an emoji now and then" if tone.emoji_rate > 0.2 else "rarely uses emojis")
    tags = ", ".join("#" + h for h in tone.top_hashtags) or "(none)"
    return f"""You write Instagram captions for the design team "{inp['team_name']}" (@{inp['handle']}).

The designer is planning this poster: "{inp['description'] or 'no description given'}"
Subject keywords: {', '.join(inp['topic']) or 'none'}
Visual mood of the poster: {', '.join(inp['mood'])}

The team's caption voice:
- about {round(tone.avg_words)} words per caption
- {emoji_habit}
- hashtags they use: {tags}
- words they use a lot: {', '.join(tone.top_words[:10]) or 'n/a'}

Their best-liked past captions (copy the VOICE only: rhythm, punctuation, emoji and hashtag habits;
they are about other events, so do not reuse their topics or phrases):
{examples}

Write {n} different captions for this poster in the same voice. Vary the opening line and the length.
Write about the poster's subject, not its colours or layout. Only use the team's own hashtags,
spelled exactly as above.
Do not invent dates, prices or names; use a placeholder like [date] if one is needed.
Return a JSON array of {n} strings and nothing else."""


def _call_gemini(prompt: str) -> list[str]:
    from google.genai import types
    resp = _gemini_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.9,
            response_mime_type="application/json",
            response_schema={"type": "ARRAY", "items": {"type": "STRING"}},
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    data = json.loads(resp.text)
    return [c.strip() for c in data if isinstance(c, str) and c.strip()]


def gemini_captions(inp: dict, tone, n: int) -> list[str] | None:
    global _cooldown_until
    if not config.USE_GEMINI:
        return None
    key = _cache_key(inp, tone, n)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if time.time() < _cooldown_until:
        log.info("Gemini rate-limited for %.0fs more; using templates",
                 _cooldown_until - time.time())
        return None

    future = _pool.submit(_call_gemini, build_prompt(inp, tone, n))
    try:
        caps = future.result(timeout=config.GEMINI_TIMEOUT_S)
    except FutureTimeout:
        log.warning("Gemini timed out after %.1fs; using templates", config.GEMINI_TIMEOUT_S)
        return None
    except Exception as e:  # network, quota, bad JSON ...
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            m = re.search(r"retry in ([\d.]+)s", msg)
            wait = float(m.group(1)) if m else 60.0
            _cooldown_until = time.time() + wait
            log.warning("Gemini quota hit; pausing it for %.0fs, using templates", wait)
        else:
            log.warning("Gemini failed (%s); using templates", msg[:200])
        return None
    if len(caps) < 2:
        return None
    caps = caps[:n]
    _cache[key] = caps
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return caps


# --------------------------------------------------------------------------
# Fallback: template captions filled from the team's own habits.
# --------------------------------------------------------------------------
HOOKS = {
    "bold": ["Big things are coming.", "Mark your calendars.", "This one's not to be missed."],
    "playful": ["Guess what's coming?", "Plot twist:", "You asked, we listened."],
    "clean and minimal": ["Simple. Focused. Coming soon.", "Less noise, more ideas."],
    "warm and energetic": ["Get ready to feel the energy!", "The countdown begins!"],
    "dark and dramatic": ["Something big is brewing.", "After dark, the real show begins."],
    "informative": ["Here's everything you need to know.", "Save this post for later."],
}
DEFAULT_HOOKS = ["Coming soon.", "Stay tuned.", "Here's what's next."]
BODIES = [
    "Featuring: {Topic}.",
    "It's all about {topic} this time, and you're invited.",
    "{Topic}, like you've never seen before.",
    "Don't miss what's next: {topic}.",
]
CTAS = ["Details in bio.", "Register now, link in bio.", "Tag a friend who should come.",
        "Save the date: [date]."]


def template_captions(inp: dict, tone, n: int) -> list[str]:
    rng = random.Random(inp.get("check_id") or 0)
    topic_words = inp["topic"][:3] or ["something new"]
    topic = " ".join(topic_words)
    hooks = [h for m in inp["mood"] for h in HOOKS.get(m, [])] + DEFAULT_HOOKS
    tags = " ".join("#" + h for h in tone.top_hashtags[:max(1, round(tone.hashtag_rate))])
    emoji = tone.top_emojis[0] if tone.emoji_rate >= 0.5 and tone.top_emojis else ""
    long_voice = tone.avg_words > 25

    out, used = [], set()
    for i in range(n * 3):
        if len(out) == n:
            break
        hook = hooks[i % len(hooks)] if i < len(hooks) else rng.choice(hooks)
        body = BODIES[i % len(BODIES)].format(topic=topic, Topic=topic.capitalize())
        parts = [hook, body]
        if long_voice:
            parts.append(rng.choice(CTAS))
        text = " ".join(parts)
        if emoji:
            text += " " + emoji
        if tags:
            text += "\n\n" + tags
        if text not in used:
            used.add(text)
            out.append(text)
    return out


def generate(inp: dict, tone, n: int = config.N_CAPTIONS) -> tuple[list[str], str]:
    caps = gemini_captions(inp, tone, n)
    if caps:
        return caps, "gemini"
    return template_captions(inp, tone, n), "template"
