"""
GIKI-Connect — course project app (social siloing + society bridge + interest-led ties).

Flask serves the UI and APIs; joblib pickles in output/model/ match the notebook pipeline.
Suggests admin-posted events and anonymized peer ideas from output/combined_with_clusters.csv.

Run: python app_server.py  or  START_APP.bat
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import socket
from urllib.parse import urlparse
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
ASSETS = PUBLIC / "assets"
MODEL_DIR = ROOT / "output" / "model"
COHORT_CSV = ROOT / "output" / "combined_with_clusters.csv"
EVENTS_SEED = ROOT / "data" / "events.json"


def events_json_path() -> Path:
    """Vercel serverless filesystem is read-only except /tmp — store mutable events there."""
    if os.environ.get("VERCEL", ""):
        p = Path("/tmp") / "giki-connect" / "events.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return EVENTS_SEED

# Change in production; for local demo only.
ADMIN_TOKEN = os.environ.get("GIKI_ADMIN_TOKEN", "giki-admin-demo")

HOBBIES = [
    "Music",
    "Art",
    "Cooking",
    "Fitness",
    "Football",
    "Hiking",
    "Coding / Programming",
    "Reading",
    "Debating",
    "Gaming",
    "Cricket",
    "Photography",
    "Travelling",
    "Skating",
]

_cohort: list[dict] = []

# Populated from cohort CSV for demo form (faculty / year pickers).
_FORM_FACULTIES: list[str] = []
_FORM_YEARS: list[str] = []

# Shown in /api/tribes — helps admins map events to clusters (ids 0–7 when K=8).
TRIBE_ADMIN_GUIDE = {
    "0": "Music & fitness crossover — gym playlists, short acoustic sets after workouts.",
    "1": "Football & music — small-sided pitch sessions plus shared playlists or half-time debriefs.",
    "2": "Cooking & reading — themed potlucks with a short book or article to react to together.",
    "3": "Art & coding — maker tables, sketch jams, or light prototyping sprints in pairs.",
    "4": "Cricket & music — nets or fielding drills with a relaxed music corner between overs.",
    "5": "Debating & hiking — trail walks with one structured prompt or timed mini-debates at the top.",
    "6": "Music & travel — trip-planning cafés, budget-hack boards, playlist swaps before breaks.",
    "7": "Skating & art — rink meetups plus quick sketch prompts or photo walks nearby.",
}

# Student-facing copy aligned with the course proposal (siloing, society bridge, interest-led ties).
CAMPUS_CONTEXT = {
    "why_title": "What this is about",
    "why": [
        "GIKI is a residential campus, but many students still sit in small circles tied to faculty, province, or batch.",
        "Societies and hobby spaces are the usual “bridge” out of those bubbles—shared interests before shared demographics.",
        "Treat the suggestions like a curated bulletin—pick what fits your week; they are hints, not a verdict on your social life.",
    ],
    "limits_title": "Keep in mind",
    "limits": [
        "Suggestions are a campus pilot, not a directory—names are anonymized and you should always use good judgment.",
        "One profile does not define you; treat tribes as a light hint, not a label.",
        "Events are posted by admins in the demo—check society boards and official notices for real logistics.",
    ],
    "next_title": "Worth trying next",
    "next": [
        "Pick one event below and aim to greet two people you do not already hang out with.",
        "If you are not in a society yet, try one intro or taster session this month—it is the fastest on-campus bridge between faculties.",
        "If you already are in a society, bring one friend who is not; international and junior-year students often benefit most from that invite.",
    ],
}


def _year_display_label(raw: str) -> str:
    """Friendly year label for forms and cards (cohort CSV may use longer wording)."""
    s = (raw or "").strip()
    if s == "1st Year (Freshie)":
        return "1st Year"
    return s


def hobby_col(h: str) -> str:
    return f"h_{h.replace(' ', '_').replace('/', '').replace(',', '')}"


# Short activity-format hints keyed to survey hobby labels (used in /api/predict copy only).
HOBBY_MICRO_TIPS = {
    "Music": "Try turn-taking formats (listening round, low-stakes open mic) so conversation is not only small talk.",
    "Art": "Sketch-walks or timed collage blocks give people something to point at while they chat.",
    "Cooking": "Potluck prep or one shared recipe keeps hands busy and lowers pressure to perform socially.",
    "Fitness": "Pair warm-ups or short relay formats avoid one person leading the whole hour.",
    "Football": "Small-sided games or skills drills create natural rotation between faces.",
    "Hiking": "Pick a route with a clear halfway landmark so pairs can split and regroup comfortably.",
    "Coding / Programming": "Pairing, mini demos, or bug hunts carry half the conversation in the work itself.",
    "Reading": "Themed chapters or 20-minute silent blocks plus one debrief line keep introverts in the loop.",
    "Debating": "Rotating prep roles and timed floor splits quieter voices in fairly.",
    "Gaming": "Co-op rounds or board-game corners let people join without monopolising the mic.",
    "Cricket": "Net sessions or fielding drills mix skill levels without awkward lulls.",
    "Photography": "Photo walks with a shared prompt card beat unstructured mingling for first contact.",
    "Travelling": "Itinerary snippets or budget hacks are easy icebreakers before deeper travel talk.",
    "Skating": "Beginner lanes or buddy checks make repeat contact natural across weeks.",
}


def _society_chips_list(societies: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for part in (societies or "").split(","):
        p = part.strip()
        if p and p not in out:
            out.append(p[:80])
        if len(out) >= limit:
            break
    return out


def _hobby_sig(label: str) -> str:
    """Loose key so 'Coding / Programming' matches notebook 'Coding  Programming'."""
    return "".join(c.lower() for c in str(label) if c.isalnum())


def _hobbies_overlap_tribe(user_hobbies: list[str], top_hobbies: list[str]) -> list[str]:
    tops = [_hobby_sig(t) for t in top_hobbies]
    out: list[str] = []
    for h in user_hobbies:
        hs = _hobby_sig(h)
        if not hs:
            continue
        for i, ts in enumerate(tops):
            if hs == ts or (len(hs) >= 8 and (hs in ts or ts in hs)):
                out.append(h)
                break
    return list(dict.fromkeys(out))


def _score_event_shapes(
    hobbies: list[str],
    silo: float,
    comfort: float,
) -> list[str]:
    """Rank generic event formats by overlap with the user's checked hobbies + silo/comfort (not cluster rotation)."""
    shapes: list[tuple[str, set[str], float]] = [
        (
            "Quiet café blocks with optional show-and-tell at the end",
            {"Reading", "Debating", "Cooking", "Music"},
            1.6 if silo >= 0.5 else 0.9,
        ),
        (
            "Short co-design jams blending visual and systems thinking",
            {"Coding / Programming", "Art", "Photography", "Fitness"},
            1.1 + (0.5 if comfort >= 4 else 0.0),
        ),
        (
            "Maker tables with parallel stations (art, board games, light prototyping)",
            {"Gaming", "Art", "Football", "Cricket", "Music", "Skating"},
            1.2 + (0.4 if silo >= 0.45 else 0.0),
        ),
        (
            "Reading or game nights with themed corners people drift between",
            {"Reading", "Gaming", "Debating", "Travelling"},
            1.0 + (0.5 if comfort >= 3.5 else 0.0),
        ),
        (
            "Outdoor segments paired with a lightweight shared task",
            {"Hiking", "Football", "Cricket", "Fitness", "Skating", "Travelling"},
            1.3 + (0.35 if silo < 0.45 else 0.0),
        ),
    ]
    hset = set(hobbies)
    scored: list[tuple[float, int, str]] = []
    for i, (text, related, base) in enumerate(shapes):
        overlap = len(hset & related)
        score = base + overlap * 2.2 + (0.35 if overlap == 0 and comfort >= 4.5 else 0.0)
        scored.append((score, i, text))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, _, t in scored[:3]]


def build_insight_sections(
    _cluster: int,
    prof: dict,
    silo: float,
    silo_lbl: str,
    comfort: float,
    soc_hours: float,
    hobbies: list[str],
    societies: str,
    same_prov_pct: float,
    same_fac_pct: float,
    friends: float,
    soc_member: bool,
) -> list[dict]:
    """Rule-based narrative from this submission's sliders, hobbies, societies, and cluster profile."""
    top = [str(h) for h in prof.get("top_hobbies") or []]
    cohort_silo = float(prof.get("avg_silo") or 0.5)
    delta = silo - cohort_silo
    sp = max(0.0, min(100.0, float(same_prov_pct)))
    sf = max(0.0, min(100.0, float(same_fac_pct)))
    fr = max(0.5, min(20.0, float(friends)))
    cm = max(1.0, min(5.0, float(comfort)))
    sh = max(0.0, float(soc_hours))
    chips = _society_chips_list(societies)

    member_txt = "yes" if soc_member else "no"
    hobby_list = ", ".join(hobbies[:10]) + ("…" if len(hobbies) > 10 else "")
    key_bullets: list[str] = [
        f"Your inputs this run: comfort {cm:.0f}/5; society member {member_txt}, society hours {sh:.1f} h/wk used for your tribe match; "
        f"{len(hobbies)} hobby pick(s): {hobby_list}; ~{fr:.1f} close friends; {sp:.0f}% same-province and {sf:.0f}% same-faculty among close friends "
        f"→ silo index {silo:.3f} ({silo_lbl}).",
    ]

    if cm < 3:
        key_bullets.append(
            f"Because comfort is {cm:.0f}/5, favour short, task-led invites (one lab chunk, a 20-minute walk) before proposing big group plans."
        )
    elif cm <= 4.25:
        key_bullets.append(
            f"Comfort {cm:.0f}/5 sits mid-band—pair regular hangouts with one new context a month so growth does not feel abrupt."
        )
    else:
        key_bullets.append(
            f"Comfort {cm:.0f}/5 is on the open side—rotating prompts or parallel mini-activities still give quieter peers a clear way in."
        )

    if silo >= 0.55:
        key_bullets.append(
            f"Silo {silo:.3f} is relatively high—add light structure (prompt card, timed turns, side-by-side tasks) so conversation is not only open mic."
        )
    elif silo < 0.35:
        key_bullets.append(
            f"Silo {silo:.3f} skews lower—good base for mixed-faculty hangs; still give newcomers one concrete first task when they arrive."
        )
    else:
        key_bullets.append(
            f"Silo {silo:.3f} sits between the extremes—balance repeat faces with one fresh context when you schedule the week."
        )

    key_bullets = key_bullets[:4]

    hobby_bullets: list[str] = []
    overlap_h = _hobbies_overlap_tribe(hobbies, top)
    if overlap_h:
        hobby_bullets.append(
            "Overlap with this tribe’s top survey hobbies on "
            + ", ".join(overlap_h)
            + "—lead with those when you message or plan a hangout."
        )
    else:
        hobby_bullets.append(
            "None of your checked hobbies match this tribe’s top-3 survey labels word-for-word—"
            f"tribe tops here are {', '.join(top[:3])}; use your picks below as the bridge you bring to the room."
        )

    ordered_h = list(dict.fromkeys([*overlap_h, *[h for h in hobbies if h not in overlap_h]]))
    for h in ordered_h:
        tip = HOBBY_MICRO_TIPS.get(h)
        if tip:
            hobby_bullets.append(f"{h}: {tip}")
    if len(hobby_bullets) < 2:
        hobby_bullets.append(
            "Pick one visible shared task for the first meet so the activity carries part of the conversation."
        )
    hobby_bullets = hobby_bullets[:6]

    society_bullets: list[str] = []
    if soc_member:
        if chips:
            society_bullets.append(
                f"You listed society chips: {', '.join(chips)} — they do not change your tribe number here; they only shape this narrative."
            )
        else:
            society_bullets.append(
                "You marked society member but left society chips empty—add names next time if you want this block to mirror your clubs."
            )
        if sh >= 2.5:
            society_bullets.append(
                f"At {sh:.1f} h/wk in societies, repeating the same meet twice beats a one-off mega-event you skip afterward."
            )
        elif sh < 1.0:
            society_bullets.append(
                f"Society hours are low ({sh:.1f} h/wk in the form)—if you want more cross-faculty ties, try one desk session or taster this month."
            )
    else:
        society_bullets.append(
            "You chose not a society member — society hours are counted as zero for your tribe match; chips are ignored here."
        )
        if sh == 0:
            society_bullets.append(
                "If you join later, re-run with member + hours so event and peer suggestions can line up with that story."
            )

    if cm < 3.5 and soc_member:
        society_bullets.append(
            "With comfort under 3.5/5, post one specific line in a society channel (e.g. “20-min walk to revise Topic X”) instead of a vague “anyone free?”."
        )
    elif cm >= 4 and chips:
        society_bullets.append(
            f"Comfort {cm:.0f}/5 plus named societies—good moment to co-host a small hobby-led invite and pull one person from another program."
        )

    society_bullets = society_bullets[:5]

    cohort_bullets = [
        f"This tribe ({prof.get('name', '')}) averages {cohort_silo:.3f} friendship concentration in the survey sample; "
        f"your silo from this form is {silo:.3f} ({silo_lbl}), Δ vs cohort ≈ {delta:+.3f}.",
    ]
    if delta > 0.08:
        cohort_bullets.append(
            "That puts you above this tribe’s survey average—structured activities may feel easier than very open rooms."
        )
    elif delta < -0.08:
        cohort_bullets.append(
            "That puts you below this tribe’s survey average—strong footing for small hobby-led hangs that widen others’ circles."
        )
    else:
        cohort_bullets.append(
            "You are near this tribe’s survey average—blend familiar faces with one new context when you plan the week."
        )

    picked_shapes = _score_event_shapes(hobbies, silo, comfort)

    sections: list[dict] = [
        {
            "id": "key_pointers",
            "title": "Key pointers",
            "bullets": key_bullets,
            "footnote": "Derived from your sliders, comfort score, and this tribe’s averages in the survey sample—not a clinical assessment.",
        },
        {
            "id": "hobby_formats",
            "title": "Your hobbies → formats that fit",
            "bullets": hobby_bullets,
        },
        {
            "id": "societies_newcomers",
            "title": "Societies & newcomers",
            "bullets": society_bullets,
        },
        {
            "id": "cohort_compare",
            "title": "You vs this tribe in the survey data",
            "bullets": cohort_bullets,
        },
        {
            "id": "event_shapes",
            "title": "Event shapes that tend to fit",
            "subtitle": "Ranked from your hobbies and how open or tight your friendship pattern feels—not from the tribe name alone.",
            "bullets": picked_shapes,
        },
    ]
    return sections


def silo_index_from_report(friends: float, same_prov_pct: float, same_fac_pct: float) -> float:
    """Report definition: (# close friends same province OR same faculty) / (total close friends).

    Survey stores marginal % only. Estimated union count (independence for overlap):
    n_or = T * (p + f - p*f) with p,f in [0,1]. Silo_Index = n_or / T = p + f - p*f.
    If T <= 0, return the union fraction only.
    """
    p = max(0.0, min(1.0, float(same_prov_pct) / 100.0))
    fp = max(0.0, min(1.0, float(same_fac_pct) / 100.0))
    t = float(friends)
    union_frac = p + fp - p * fp
    if t <= 0:
        return round(max(0.0, min(1.0, union_frac)), 3)
    n_or = t * union_frac
    return round(max(0.0, min(1.0, n_or / t)), 3)


def _polish_tribe_display_fields(prof: dict) -> None:
    """Notebook CSV uses 'Coding  Programming'; UI and forms use slashes."""
    name = prof.get("name")
    if isinstance(name, str):
        prof["name"] = name.replace("Coding  Programming", "Coding / Programming")
    tops = prof.get("top_hobbies")
    if isinstance(tops, list):
        prof["top_hobbies"] = [
            h.replace("Coding  Programming", "Coding / Programming") if isinstance(h, str) else h
            for h in tops
        ]


def load_artifacts():
    global km_model_data, feature_cols, cluster_profiles
    with open(PUBLIC / "model_data.json", encoding="utf-8") as f:
        km_model_data = json.load(f)
    
    feature_cols = km_model_data["feature_cols"]
    cluster_profiles = km_model_data["cluster_profiles"]
    
    for prof in cluster_profiles.values():
        if isinstance(prof, dict):
            _polish_tribe_display_fields(prof)


def _unique_csv_column(path: Path, column: str) -> list[str]:
    if not path.is_file():
        return []
    seen: set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = (row.get(column) or "").strip()
            if v:
                seen.add(v)
    return sorted(seen)


def load_cohort():
    global _cohort, _FORM_FACULTIES, _FORM_YEARS
    _cohort = []
    _FORM_FACULTIES = []
    _FORM_YEARS = []
    if not COHORT_CSV.is_file():
        return
    with open(COHORT_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["_cluster"] = int(float(row.get("Cluster", -1)))
            except (TypeError, ValueError):
                continue
            _cohort.append(row)
    _FORM_FACULTIES = _unique_csv_column(COHORT_CSV, "Faculty")
    _FORM_YEARS = sorted({_year_display_label(y) for y in _unique_csv_column(COHORT_CSV, "Year")})


def training_meta() -> dict:
    """Live numbers for demo banner — matches saved model & cohort."""
    total_n = sum(int(p["n"]) for p in cluster_profiles.values())
    return {
        "k_clusters": len(cluster_profiles),
        "total_profiles": total_n,
    }


def load_events_file() -> dict:
    path = events_json_path()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        if EVENTS_SEED.is_file() and path.resolve() != EVENTS_SEED.resolve():
            shutil.copy2(EVENTS_SEED, path)
        elif not path.is_file():
            path.write_text('{"events":[]}', encoding="utf-8")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_events_file(data: dict) -> None:
    path = events_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def suggest_peers(cluster: int, hobbies: list[str], limit: int = 6) -> list[dict]:
    if not _cohort:
        return []
    want = set(hobbies)
    scored: list[tuple[int, dict]] = []
    for row in _cohort:
        if row.get("_cluster") != cluster:
            continue
        raw_h = row.get("Hobbies") or ""
        theirs = {x.strip() for x in raw_h.replace(";", ",").split(",") if x.strip()}
        overlap = len(want & theirs)
        reg = str(row.get("Reg", "")).strip()
        if reg.upper().startswith("ANON"):
            display = reg
        else:
            display = f"Student …{reg[-4:]}" if len(reg) >= 4 else "Student"
        soc_cell = str(row.get("Societies") or "").strip()
        society_cue = soc_cell.split(",")[0].strip()[:56] if soc_cell else ""
        scored.append(
            (
                overlap,
                {
                    "display": display,
                    "faculty": row.get("Faculty", ""),
                    "province": row.get("Province", ""),
                    "year": _year_display_label(str(row.get("Year") or "")),
                    "hobbies_preview": ", ".join(sorted(theirs)[:6]),
                    "shared_hobbies": sorted(want & theirs),
                    "overlap": overlap,
                    "society_cue": society_cue,
                },
            )
        )
    scored.sort(key=lambda x: (-x[0], x[1]["display"]))
    return [p for _, p in scored[:limit]]


def suggest_events(cluster: int, hobbies: list[str]) -> list[dict]:
    data = load_events_file()
    events = data.get("events") or []
    hs = set(hobbies)
    scored: list[tuple[float, dict]] = []
    for e in events:
        tags = set(e.get("hobby_tags") or [])
        clusters = e.get("clusters") or []
        overlap = len(hs & tags)
        c_bonus = 2.0 if cluster in clusters else (0.5 if not clusters else 0.0)
        score = overlap * 3 + c_bonus
        scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    picked = [dict(e) for s, e in scored if s > 0][:8]
    if not picked:
        picked = [dict(e) for s, e in scored[:5]]
    return picked


def tribes_payload() -> dict:
    """Single payload for UI: tribe atlas + campus narrative (cluster_profiles loaded)."""
    tribes = []
    for key in sorted(cluster_profiles.keys(), key=lambda x: int(x)):
        p = cluster_profiles[key]
        tribes.append(
            {
                "id": int(key),
                "name": p["name"],
                "n": p["n"],
                "avg_silo": p["avg_silo"],
                "top_hobbies": p["top_hobbies"],
                "admin_guide": TRIBE_ADMIN_GUIDE.get(
                    str(key),
                    "Match event hobbies to this tribe’s top interests.",
                ),
            }
        )
    return {
        "tribes": tribes,
        "kmeans_note": "",
        **CAMPUS_CONTEXT,
    }


def predict_row(
    hobbies: list[str],
    soc_hours: float,
    comfort: float,
    same_prov_pct: float,
    same_fac_pct: float,
    friends: float = 4.0,
    societies: str = "",
    soc_member: bool = True,
):
    sel = set(hobbies)
    row = {}
    for h in HOBBIES:
        key = hobby_col(h)
        row[key] = 1 if h in sel else 0
    row["SocHours"] = float(soc_hours)
    row["ComfortScore"] = float(comfort)
    silo = silo_index_from_report(friends, same_prov_pct, same_fac_pct)
    row["Silo_Index"] = silo

    vec = [float(row.get(c, 0.0)) for c in feature_cols]
    for i in range(len(vec)):
        vec[i] = (vec[i] - km_model_data["scaler_mean"][i]) / km_model_data["scaler_scale"][i]

    best_dist = float("inf")
    cluster = 0
    for idx, center in enumerate(km_model_data["cluster_centers"]):
        dist = sum((center[i] - vec[i]) ** 2 for i in range(len(vec)))
        if dist < best_dist:
            best_dist = dist
            cluster = idx
    if silo < 0.25:
        silo_lbl = "Low (diverse)"
    elif silo < 0.5:
        silo_lbl = "Moderate"
    else:
        silo_lbl = "High (siloed)"

    prof = cluster_profiles[str(cluster)]
    if silo > 0.5:
        rec = (
            f"Silo index {silo:.2f} ({silo_lbl}) from your {same_prov_pct:.0f}% / {same_fac_pct:.0f}% / ~{friends:.0f} friends inputs looks concentrated—"
            "try one society taster or cross-faculty mixer this week and add one contact outside your usual batch."
        )
    elif (not soc_member) or soc_hours < 1.0:
        rec = (
            f"Society side is light in this run (member={soc_member}, hours={soc_hours:.1f} h/wk)—"
            "if you can, one society desk or open event is often the fastest bridge between faculties."
        )
    else:
        rec = (
            f"Silo {silo:.2f} with comfort {comfort:.0f}/5 and {soc_hours:.1f} society h/wk—"
            "use the matched events list to host or co-host a small hobby hangout and invite someone from another program."
        )
    peers = suggest_peers(cluster, hobbies)
    events = suggest_events(cluster, hobbies)
    insight_sections = build_insight_sections(
        cluster,
        prof,
        silo,
        silo_lbl,
        comfort,
        soc_hours,
        hobbies,
        societies,
        same_prov_pct,
        same_fac_pct,
        friends,
        soc_member,
    )
    k_all = len(cluster_profiles)
    assignment_explain = {
        "title": "How your tribe was chosen",
        "lines": [
            (
                f"You are in tribe {cluster} (out of {k_all}). The name \"{prof['name']}\" and the "
                f"{prof['n']} people in that group come from the same survey analysis that powers this demo."
            ),
            (
                "The form turns your hobbies, society hours, comfort score, and friendship-pattern sliders into one profile; "
                "that profile is compared to the saved survey-based tribes, and you are placed in the closest match."
            ),
            (
                "Faculty, year, and society names you typed are kept with your answers for your own records, "
                "but they do not change the tribe number unless the project is rebuilt with new analysis."
            ),
        ],
    }
    return {
        "cluster": cluster,
        "tribe_name": prof["name"],
        "tribe_size": prof["n"],
        "tribe_avg_silo": prof["avg_silo"],
        "top_hobbies": prof["top_hobbies"],
        "silo_index": silo,
        "silo_label": silo_lbl,
        "comfort_used": comfort,
        "soc_hours_used": soc_hours,
        "recommendation": rec,
        "suggested_peers": peers,
        "suggested_events": events,
        "insight_sections": insight_sections,
        "assignment_explain": assignment_explain,
        "result_footer": (
            "The story blocks under your result mix your answers, your tribe label, and simple rules from the survey sample — "
            "they are not a second automated model."
        ),
        "model_note": "",
    }


app = Flask(
    __name__,
    static_folder=str(ASSETS),
    static_url_path="/assets",
)


def _dev_cors_origin_allowed(origin: str) -> bool:
    """Allow browser tools (e.g. Live Preview) on localhost to call the API when not on Vercel."""
    try:
        p = urlparse(origin)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "[::1]")


@app.after_request
def _dev_cors_headers(response):
    if os.environ.get("VERCEL", ""):
        return response
    origin = request.headers.get("Origin", "")
    if origin and _dev_cors_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@app.get("/")
def index():
    return send_from_directory(str(PUBLIC), "index.html")


@app.get("/api/index")
@app.get("/api/index/")
def _legacy_vercel_index_alias():
    """If an old deployment still rewrites to /api/index, serve the same home page."""
    return send_from_directory(str(PUBLIC), "index.html")


@app.get("/api/tribes")
def api_tribes():
    """Tribe definitions + campus narrative for student insight and admin event targeting."""
    return jsonify(tribes_payload())


@app.get("/api/meta")
def api_meta():
    """Demo stats + form dropdown options (faculty / year from cohort CSV)."""
    return jsonify(
        {
            **training_meta(),
            "faculties": _FORM_FACULTIES,
            "years": _FORM_YEARS,
        }
    )


@app.get("/api/events")
def api_events_list():
    return jsonify(load_events_file())


@app.route("/api/events", methods=["POST", "OPTIONS"])
def api_events_create():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.headers.get("X-Admin-Token", "") != ADMIN_TOKEN:
        return jsonify({"error": "Admin token required (header X-Admin-Token)."}), 403
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    when_iso = (data.get("when_iso") or "").strip()
    place = (data.get("place") or "").strip()
    description = (data.get("description") or "").strip()
    hobby_tags = [str(x) for x in (data.get("hobby_tags") or []) if str(x) in HOBBIES]
    clusters_raw = data.get("clusters") or []
    clusters: list[int] = []
    for c in clusters_raw:
        try:
            clusters.append(int(c))
        except (TypeError, ValueError):
            continue
    if not title or not when_iso:
        return jsonify({"error": "title and when_iso are required."}), 400
    store = load_events_file()
    ev = {
        "id": str(uuid.uuid4())[:12],
        "title": title,
        "when_iso": when_iso,
        "place": place,
        "description": description,
        "hobby_tags": hobby_tags,
        "clusters": clusters,
    }
    store.setdefault("events", []).insert(0, ev)
    save_events_file(store)
    return jsonify({"ok": True, "event": ev})


@app.route("/api/predict", methods=["POST", "OPTIONS"])
def api_predict():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        data = request.get_json(force=True, silent=True) or {}
        hobbies = data.get("hobbies") or []
        if not isinstance(hobbies, list):
            return jsonify({"error": "hobbies must be a list"}), 400
        hobbies = [str(h) for h in hobbies if str(h) in HOBBIES]
        try:
            soc = float(data.get("soc_hours", 0))
            comfort = float(data.get("comfort", 4))
            sp = float(data.get("same_prov_pct", 50))
            sf = float(data.get("same_fac_pct", 50))
            friends = float(data.get("friends", 4))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid numeric fields"}), 400

        soc_member_raw = data.get("soc_member", True)
        if isinstance(soc_member_raw, str):
            soc_member = soc_member_raw.strip().lower() in ("yes", "true", "1", "y", "member")
        else:
            soc_member = bool(soc_member_raw)
        if not soc_member:
            soc = 0.0

        soc = max(0.0, min(soc, 20.0))
        comfort = max(1.0, min(comfort, 5.0))
        sp = max(0.0, min(sp, 100.0))
        sf = max(0.0, min(sf, 100.0))
        friends = max(0.5, min(friends, 20.0))

        if not hobbies:
            return jsonify({"error": "Pick at least one hobby."}), 400

        societies_in = str(data.get("societies") or "").strip()[:500]
        out = predict_row(hobbies, soc, comfort, sp, sf, friends, societies_in, soc_member)
        out["submitted"] = {
            "faculty": str(data.get("faculty") or "").strip()[:120],
            "year": str(data.get("year") or "").strip()[:80],
            "soc_member": soc_member,
            "societies": societies_in,
        }
        return jsonify(out)
    except Exception as e:
        # Always JSON so the browser can parse errors (HTML 500 breaks fetch().json()).
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


def _pick_port(start: int = 8765, attempts: int = 25) -> int:
    for port in range(start, start + attempts):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    raise SystemExit("No free TCP port found in range — close other apps using 8765–8790.")


def main():
    if not (PUBLIC / "model_data.json").exists():
        raise SystemExit(
            f"Missing model_data.json. Run export scripts first."
        )
    load_artifacts()
    load_cohort()
    port = _pick_port()
    base = f"http://127.0.0.1:{port}"
    url = f"{base}/"

    def _open_browser():
        time.sleep(1.8)
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    print()
    print("=" * 56)
    print("  GIKI-Connect — SERVER IS RUNNING")
    print("=" * 56)
    print(f"  App:     {url}")
    print(f"  Admin:   post events with header X-Admin-Token: {ADMIN_TOKEN}")
    print("  (Set GIKI_ADMIN_TOKEN env var to change the demo token.)")
    print("  Keep this window open. Ctrl+C to stop.")
    print("=" * 56)
    print()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def _bootstrap_model():
    """Load pickles when the module is imported (needed for Vercel — no main() run)."""
    if (PUBLIC / "model_data.json").is_file():
        load_artifacts()
        load_cohort()


_bootstrap_model()


if __name__ == "__main__":
    main()
