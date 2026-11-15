"""Adaptive part: learn each team's caption voice and what earns likes.

TeamTone        - TF-IDF vocabulary + style statistics of the team's past captions.
EngagementModel - ridge regression: caption features -> log(likes).
Both are rebuilt from the SQLite posts table on every check, so they adapt as
more of the team's posts arrive.
"""
import math
from collections import Counter

import numpy as np

import etl


class TeamTone:
    def __init__(self, posts: list[dict]):
        self.posts = [p for p in posts if p.get("clean_text")]
        self.n = len(self.posts)
        docs = [etl.tokenize(p["clean_text"]) for p in self.posts]

        df = Counter(w for d in docs for w in set(d))
        self.idf = {w: math.log((1 + self.n) / (1 + c)) + 1 for w, c in df.items()}
        self.vectors = [self._vec(d) for d in docs]

        words = [p["n_words"] for p in self.posts] or [25]
        self.avg_words = float(np.mean(words))
        self.std_words = float(np.std(words)) or 8.0
        self.emoji_rate = float(np.mean([len(p["emojis"]) for p in self.posts])) if self.n else 0.0
        self.hashtag_rate = float(np.mean([len(p["hashtags"]) for p in self.posts])) if self.n else 0.0
        # Count case-insensitively but show the spelling the team uses (#Techkriti).
        spelling = {}
        for p in self.posts:
            for raw in etl.HASHTAG_RE.findall(p.get("caption") or ""):
                spelling.setdefault(raw.lower(), raw)
        self.top_hashtags = [spelling.get(h, h) for h, _ in Counter(
            h for p in self.posts for h in dict.fromkeys(p["hashtags"])).most_common(6)]
        self.top_emojis = [e for e, _ in Counter(
            e for p in self.posts for e in p["emojis"]).most_common(5)]
        self.top_words = [w for w, _ in Counter(w for d in docs for w in d).most_common(15)]
        # How similar the team's own captions are to each other: the yardstick
        # that turns raw cosine similarity into a 0-100 "sounds like us" score.
        self.ref_sim = self._reference_similarity()

    # --- vocabulary -------------------------------------------------------
    def _vec(self, tokens: list[str]) -> dict:
        tf = Counter(tokens)
        v = {w: c * self.idf.get(w, math.log(1 + self.n) + 1) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    @staticmethod
    def _cos(a: dict, b: dict) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(w, 0.0) for w, x in a.items())

    def _top_k_sim(self, vec: dict, exclude: int | None = None, k: int = 3) -> float:
        sims = sorted((self._cos(vec, v) for i, v in enumerate(self.vectors) if i != exclude),
                      reverse=True)
        return float(np.mean(sims[:k])) if sims else 0.0

    def _reference_similarity(self) -> float:
        if self.n < 3:
            return 0.25
        ref = float(np.mean([self._top_k_sim(v, exclude=i) for i, v in enumerate(self.vectors)]))
        return max(ref, 0.05)

    def vocab_match(self, caption: str) -> float:
        """0-1: how close the wording is to the team's captions, relative to how
        close their own captions are to each other."""
        if self.n == 0:
            return 0.5
        sim = self._top_k_sim(self._vec(etl.tokenize(caption)))
        return min(1.0, sim / self.ref_sim)

    # --- style statistics -------------------------------------------------
    def style_match(self, c: dict) -> float:
        """0-1: length, emoji and hashtag habits compared with the team's."""
        length = math.exp(-((c["n_words"] - self.avg_words) / (2 * self.std_words)) ** 2)
        emoji = math.exp(-abs(len(c["emojis"]) - self.emoji_rate) / 2)
        tags = math.exp(-abs(len(c["hashtags"]) - self.hashtag_rate) / 3)
        team_tags = {h.lower() for h in self.top_hashtags}
        own_tags = (sum(h in team_tags for h in c["hashtags"]) / len(c["hashtags"])
                    if c["hashtags"] else (1.0 if self.hashtag_rate < 0.5 else 0.5))
        return 0.4 * length + 0.2 * emoji + 0.2 * tags + 0.2 * own_tags

    def tone_match(self, caption: str) -> float:
        """0-100 alignment with the team's preferred tone."""
        c = etl.clean_caption(caption)
        return round(100 * (0.6 * self.vocab_match(c["clean_text"]) + 0.4 * self.style_match(c)), 1)


class EngagementModel:
    """Ridge regression on simple caption features, trained per team."""
    MIN_POSTS = 8
    LAMBDA = 1.0

    def __init__(self, posts: list[dict], tone: TeamTone):
        self.tone = tone
        data = [p for p in posts if p.get("likes") is not None and p.get("clean_text")]
        self.n = len(data)
        self.median_likes = float(np.median([p["likes"] for p in data])) if data else None
        self.ready = self.n >= self.MIN_POSTS
        if not self.ready:
            return
        X = np.array([self._features(etl.clean_caption(p["caption"])) for p in data])
        y = np.log1p([p["likes"] for p in data])
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = np.hstack([np.ones((self.n, 1)), (X - self.mu) / self.sd])
        reg = self.LAMBDA * np.eye(Z.shape[1])
        reg[0, 0] = 0.0                      # don't shrink the intercept
        self.w = np.linalg.solve(Z.T @ Z + reg, Z.T @ y)

    def _features(self, c: dict) -> list[float]:
        return [
            math.log1p(c["n_words"]),
            len(c["hashtags"]),
            len(c["emojis"]),
            float(c["has_question"]),
            float(c["has_exclaim"]),
            c["n_lines"],
            self.tone.vocab_match(c["clean_text"]),
        ]

    def predict_likes(self, caption: str) -> float | None:
        if not self.ready:
            return None
        x = (np.array(self._features(etl.clean_caption(caption))) - self.mu) / self.sd
        return round(float(np.expm1(self.w[0] + x @ self.w[1:])), 0)
