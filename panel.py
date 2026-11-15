"""Build the Panel JSON that VibeCheck draws."""

TITLE = "Caption Suggester"


def build_panel(inp: dict, scored: list[dict], tone, model, source: str) -> dict:
    best = scored[0]
    n_kw = len(inp["topic"])
    src = "Gemini" if source == "gemini" else "built-in templates (Gemini unavailable)"

    metrics = [
        {"label": "Best tone match", "value": best["tone_match"], "unit": "/100"},
        {"label": "Keywords used (best)", "value": f"{best['keyword_hits']} of {n_kw}"},
        {"label": "Captions learned from", "value": tone.n},
    ]
    if best["pred_likes"] is not None:
        metrics.insert(2, {"label": "Predicted likes (best)", "value": int(best["pred_likes"]),
                           "unit": f" (usual {int(model.median_likes)})"})

    items = []
    for i, s in enumerate(scored, 1):
        prefix = f"Caption {i}" + (" (best fit)" if i == 1 else "")
        items.append({"ok": True if i == 1 else None,
                      "text": f"{prefix}: {s['caption']}"})
    if tone.n < 3:
        items.append({"ok": False, "text": "Few past captions for this team yet, so the tone "
                                           "score is rough. It improves as posts are imported."})

    return {
        "title": TITLE,
        "summary": (f"{len(scored)} caption ideas in {inp['team_name']}'s voice, "
                    f"mood: {', '.join(inp['mood'])}. Written by {src}, ranked by fit."),
        "metrics": metrics,
        "items": items,
        "chart": {
            "type": "bar",
            "title": "Tone match with the team's past captions",
            "x_label": "Caption",
            "y_label": "Tone match (0-100)",
            "points": [{"label": f"Caption {i}", "value": s["tone_match"]}
                       for i, s in enumerate(scored, 1)],
        },
    }


def message_panel(text: str) -> dict:
    return {"title": TITLE, "summary": text}
