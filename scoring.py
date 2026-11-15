"""Score and rank caption suggestions."""
import etl


def keyword_hits(caption: str, keywords: list[str]) -> int:
    """How many of the description's subject keywords the caption uses
    (prefix match, so 'speaker' also counts 'speakers')."""
    words = etl.tokenize(caption)
    return sum(any(w.startswith(k) or (len(w) >= 4 and k.startswith(w)) for w in words)
               for k in keywords)


def score_captions(captions: list[str], inp: dict, tone, model) -> list[dict]:
    keywords = inp["topic"]
    scored = []
    for cap in captions:
        tm = tone.tone_match(cap)
        hits = keyword_hits(cap, keywords)
        likes = model.predict_likes(cap)
        kw_part = hits / len(keywords) if keywords else 0.5
        like_part = (min(1.5, likes / model.median_likes) / 1.5
                     if likes is not None and model.median_likes else 0.5)
        fit = round(0.5 * tm + 30 * kw_part + 20 * like_part, 1)
        scored.append({"caption": cap, "tone_match": tm, "keyword_hits": hits,
                       "pred_likes": likes, "fit": fit})
    scored.sort(key=lambda s: s["fit"], reverse=True)
    return scored
