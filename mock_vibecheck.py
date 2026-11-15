"""Tiny stand-in for VibeCheck's GET /teams/{id}/posts, for local testing only.

The captions below are made-up test data in the style of a college tech-fest page.
Run:  uvicorn mock_vibecheck:app --port 8000
"""
from fastapi import FastAPI

app = FastAPI(title="Mock VibeCheck (test data)")

CAPTIONS = [
    ("SIP > FOMO.\n\nYour first salary, your first SIP, your first step towards wealth. Join us for the FinLit session this Saturday! #Techkriti #FinLit #IITKanpur", 133),
    ("Happy National Education Day! 🇮🇳\nToday, we honor the minds that shaped modern India. #Techkriti #IITKanpur", 99),
    ("The wait is over! 🚀 Registrations for the Hackathon are now LIVE. Build, break, repeat. Link in bio. #Techkriti #Hackathon", 210),
    ("Meet our next speaker: a pioneer in space robotics. Catch the talk live at the Lecture Hall Complex. #Techkriti #TechTalks", 175),
    ("Code. Coffee. Compete. ☕ The coding marathon returns this weekend. #Techkriti #CodeWars", 160),
    ("Throwback to the energy of last year's Pronite! 🔥 Who's ready for round two? #Techkriti #IITKanpur", 240),
    ("Workshop alert! Learn drone building from scratch with hands-on sessions. Limited seats, register now. #Techkriti #Workshops", 120),
    ("Robots, rivals and one arena. Robowars is back! 🤖 #Techkriti #Robowars", 198),
    ("Ideas that change the world start here. Submit your startup pitch before Friday. #Techkriti #Startups", 88),
    ("A huge thank you to everyone who joined the AI summit! See you next year. #Techkriti #AI", 140),
    ("Your campus, your stage. Auditions for the tech-quiz are open! #Techkriti #Quiz", 76),
    ("Save the date! The biggest tech fest of North India is almost here. #Techkriti #IITKanpur", 260),
    ("Lights, lasers and a whole lot of innovation. Here's a sneak peek of the expo. ✨ #Techkriti #Expo", 185),
    ("Calling all designers! Show us your best poster in the design challenge. #Techkriti #Design", 95),
    ("Big announcement coming tomorrow. Stay tuned! 👀 #Techkriti", 150),
    ("Learn from the best: a keynote by an industry leader on the future of chips. #Techkriti #TechTalks", 130),
    ("Thank you for 50K followers! 💙 None of this happens without you. #Techkriti", 310),
    ("The countdown begins: 10 days to go! #Techkriti #IITKanpur", 170),
    ("Panel discussion: women in engineering. Join us at the auditorium. #Techkriti #WomenInTech", 110),
    ("Our first speaker session of the season, on climate tech and the road ahead. #Techkriti #TechTalks", 125),
]


@app.get("/teams/{team_id}/posts")
def posts(team_id: int, label: str | None = None, limit: int = 60, offset: int = 0):
    items = [{"id": 1000 + i, "team_id": team_id, "label": "team", "source_page": "techkriti.iitk",
              "caption": c, "likes": likes, "comments": likes // 6,
              "posted_at": f"2026-{(i % 9) + 3:02d}-{(i % 27) + 1:02d}T10:00:00"}
             for i, (c, likes) in enumerate(CAPTIONS)]
    return {"total": len(items), "items": items[offset:offset + limit]}
