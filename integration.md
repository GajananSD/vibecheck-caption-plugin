# Integrating Caption Suggester with VibeCheck

VibeCheck calls our plugin; we never touch their code. Integration means:
**our service runs → VibeCheck can reach it → we register its URL once → every check shows our panel.**

```
Designer runs a check in VibeCheck
        │
        ▼
VibeCheck ──POST check.completed──▶  our /hook  (port 8100)
        ▲                               │  ETL → tone model → Gemini → scoring
        └──────── Panel JSON ◀──────────┘  (must answer in < 5 s)
                                        │
our plugin ──GET /teams/{id}/posts──▶ VibeCheck   (background, every 30 min)
```

---

## 0. Before you start (agree with the VibeCheck team)

- [ ] Get their repo running or their server address (`$API`, e.g. `http://192.168.1.20:8000`).
- [ ] Their team must exist in VibeCheck **with a trained model** (otherwise checks fail with 409).
- [ ] Decide the demo setup: **same laptop** (easiest) or **two laptops on the same network**.
- [ ] Both demos must be in the **same slot** (Nov 16 or Nov 29).

## 1. Choose the setup

### Option A — both on one laptop (recommended for the demo)

Clone their repo (`github.com/Pro-Nil/vibecheck`) on our laptop, or ours on theirs.

| | Value |
|---|---|
| VibeCheck | `http://localhost:8000` |
| Plugin URL to register | `http://localhost:8100/hook` |

No network or firewall issues. Skip to step 2.

### Option B — two laptops on one network

Campus Wi-Fi often blocks laptop-to-laptop traffic. Use a **phone hotspot** that both laptops join.

1. Find our IP:
   ```bash
   hostname -I        # e.g. 192.168.43.57  -> use the first address
   ```
2. Open port 8100 in Fedora's firewall:
   ```bash
   sudo firewall-cmd --add-port=8100/tcp                  # until reboot
   # sudo firewall-cmd --add-port=8100/tcp --permanent && sudo firewall-cmd --reload   # permanently
   ```
3. Ask the VibeCheck team to run their server with `--host 0.0.0.0` and open port 8000 on their side.
4. Put their address in our `.env` (needed because they may send `api_base` as `localhost`):
   ```
   VIBECHECK_API_BASE=http://<their-ip>:8000
   ```

| | Value |
|---|---|
| VibeCheck | `http://<their-ip>:8000` |
| Plugin URL to register | `http://<our-ip>:8100/hook` |

## 2. Prepare the plugin

```bash
cd ~/Downloads/vibecheck_plugin
rm -f captions.db                      # remove mock/test data before a real run
source .venv/bin/activate
python -m pytest -q tests              # should say 12 passed
```

Check `.env` has `GEMINI_API_KEY` filled in.

## 3. Start the plugin

```bash
uvicorn app:app --host 0.0.0.0 --port 8100
```

Keep this terminal open: every check prints a log line like
`check 17 team 1: 4 captions via gemini in 1408 ms`.

Do **not** run `mock_vibecheck.py` now — it also uses port 8000 and would clash with real VibeCheck.

## 4. Check both directions can talk

```bash
export API=http://localhost:8000              # or http://<their-ip>:8000

curl -s $API/health                           # VibeCheck is up   -> {"ok": true, ...}
curl -s $API/teams                            # note their team id and "trained": true
curl -s http://localhost:8100/health          # plugin is up      -> {"ok": true, "gemini": true, ...}
```

Option B only — from **their** laptop:
```bash
curl -s http://<our-ip>:8100/health
```
If this hangs, it's the firewall or Wi-Fi isolation (see Troubleshooting).

## 5. Register the plugin (once)

```bash
curl -s -X POST $API/plugins -H "Content-Type: application/json" -d '{
  "name": "Caption Suggester",
  "url": "http://localhost:8100/hook",
  "slot": "result",
  "description": "On-brand Instagram caption ideas for your poster, learned from the team'\''s past captions.",
  "author_team": "<our team name>"
}'
```

- Use `http://<our-ip>:8100/hook` for Option B.
- Add `"team_id": 1` to show it for one team only; leave it out for all teams.
- Or use the **Plugins page** in the VibeCheck app instead of curl.

Confirm, and note the plugin `id`:
```bash
curl -s $API/plugins
```

## 6. Run a real check

In the VibeCheck app (or with curl), score a plan with an image and a description:
```bash
curl -s -X POST $API/teams/1/checks \
  -F "images=@poster_inspo.jpg" \
  -F "description=dark background, neon green code text, hackathon prize money in big bold numbers" \
  -F "user=demo"
```

Expected:
- [ ] Our plugin terminal logs `... captions via gemini in ... ms`.
- [ ] The **Caption Suggester** panel appears on the Result page: summary, metrics, 4 captions (best one ticked), bar chart.
- [ ] A few seconds later the log shows `Synced N captioned posts for team 1` (full history pulled).
- [ ] Run a second check: **Captions learned from** goes up and **Predicted likes** appears.

## 7. Managing the registration

```bash
curl -s -X PATCH  $API/plugins/<id> -H "Content-Type: application/json" -d '{"enabled": false}'   # hide panel
curl -s -X PATCH  $API/plugins/<id> -H "Content-Type: application/json" -d '{"url": "http://<new-ip>:8100/hook"}'  # IP changed
curl -s -X DELETE $API/plugins/<id>                                                                 # remove
```

If the hotspot gives us a new IP on demo day, update the URL with the PATCH above.

## 8. Demo-day checklist

- [ ] Same slot as the VibeCheck team; setup (A or B) agreed and rehearsed.
- [ ] `rm -f captions.db`, then start the plugin; run one warm-up check before presenting (this also syncs the team's posts).
- [ ] Gemini key works (`/health` shows `"gemini": true`).
- [ ] Space checks out: the free tier allows **~5 Gemini calls per minute**. Repeating the same idea is cached; beyond the limit the panel still works using templates (summary says "built-in templates").
- [ ] Have a phone hotspot ready in case of Wi-Fi problems.
- [ ] Show `http://localhost:8100/docs` if asked about our API.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Panel shows an error / timeout note | VibeCheck can't reach our URL, or we took > 5 s | Check step 4; check our terminal for the request; lower `GEMINI_TIMEOUT_S` in `.env` |
| No request appears in our terminal at all | Wrong URL registered, or plugin disabled | `curl $API/plugins`, fix with PATCH |
| `curl http://<our-ip>:8100/health` hangs from their laptop | Firewall or Wi-Fi client isolation | `sudo firewall-cmd --add-port=8100/tcp`; use a phone hotspot |
| Summary says "built-in templates" | Gemini quota (429), timeout or no key | Wait a minute; check `.env`; see terminal warning |
| "Captions learned from" stays small | Background sync can't reach VibeCheck | Set `VIBECHECK_API_BASE` in `.env`; look for `Could not fetch posts` in the log |
| Check itself fails with 409 | Their team has no trained model | They run `POST $API/teams/1/retrain` and wait for the job |
| `address already in use` on 8100 | Plugin already running | `pkill -f "uvicorn app:app"` and restart |
