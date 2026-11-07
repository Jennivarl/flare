#!/usr/bin/env python3
"""Relief Room: the shared crisis board that Switch agents work on.

The agents (Intake, Verify, Dispatch, Sitrep) live in a Switch room and run
these commands. The live map at http://127.0.0.1:8787 reads the same database.

Standard library only. Python 3.10+.
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("RELIEF_DB", ROOT / "data" / "relief.db"))
SCENARIO_DIR = ROOT / "scenarios"
WEB_DIR = ROOT / "web"

URGENCY_WORDS = {5: "CRITICAL", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "INFO"}
CASE_STATUSES = ["open", "verifying", "dispatched", "rescued", "closed", "rumour", "duplicate"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, source TEXT, sender TEXT, text TEXT,
  received_at TEXT, status TEXT DEFAULT 'new', case_id INTEGER
);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY, place TEXT, lat REAL, lon REAL, people INTEGER,
  needs TEXT, urgency INTEGER, lang TEXT, summary TEXT, status TEXT DEFAULT 'open',
  reports INTEGER DEFAULT 1, dup_of INTEGER, note TEXT, zone TEXT,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS resources (
  id TEXT PRIMARY KEY, kind TEXT, name TEXT, lat REAL, lon REAL,
  capacity INTEGER, status TEXT DEFAULT 'available', case_id INTEGER
);
CREATE TABLE IF NOT EXISTS dispatches (
  id INTEGER PRIMARY KEY, case_id INTEGER, resource_id TEXT, eta_min INTEGER,
  status TEXT, proposed_by TEXT, approved_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY, topic TEXT, verdict TEXT, reason TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS zones (
  name TEXT PRIMARY KEY, lat REAL, lon REAL, radius_km REAL, room TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, at TEXT, actor TEXT, kind TEXT, text TEXT
);
"""


# --------------------------------------------------------------------------- helpers

def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def log(conn, actor: str, kind: str, text: str) -> None:
    conn.execute("INSERT INTO events(at, actor, kind, text) VALUES (?,?,?,?)", (now(), actor, kind, text))


def km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def scenario_name(conn) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key='scenario'").fetchone()
    return row["value"] if row else "lagos-flood"


def gazetteer(conn) -> dict:
    path = SCENARIO_DIR / scenario_name(conn) / "places.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def out(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- setup

def cmd_init(a):
    if DB_PATH.exists():
        DB_PATH.unlink()
        for extra in (DB_PATH.with_suffix(".db-wal"), DB_PATH.with_suffix(".db-shm")):
            if extra.exists():
                extra.unlink()
    conn = db()
    sdir = SCENARIO_DIR / a.scenario
    if not sdir.exists():
        die(f"no scenario '{a.scenario}' in {SCENARIO_DIR}")
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('scenario', ?)", (a.scenario,))
    for r in json.loads((sdir / "resources.json").read_text(encoding="utf-8")):
        conn.execute(
            "INSERT INTO resources(id, kind, name, lat, lon, capacity) VALUES (?,?,?,?,?,?)",
            (r["id"], r["kind"], r["name"], r["lat"], r["lon"], r.get("capacity", 0)),
        )
    log(conn, "system", "init", f"Relief board ready: scenario {a.scenario}")
    conn.commit()
    print(f"Relief board ready ({a.scenario}). Database: {DB_PATH}")


# --------------------------------------------------------------------------- messages

def cmd_ingest(a):
    conn = db()
    cur = conn.execute(
        "INSERT INTO messages(source, sender, text, received_at) VALUES (?,?,?,?)",
        (a.source, a.sender, a.text, now()),
    )
    log(conn, a.source, "message", f"{a.sender}: {a.text[:90]}")
    conn.commit()
    print(f"message #{cur.lastrowid} stored")


def cmd_inbox(a):
    conn = db()
    msgs = rows(conn.execute(
        "SELECT id, source, sender, text, received_at FROM messages WHERE status='new' ORDER BY id LIMIT ?",
        (a.limit,),
    ))
    left = conn.execute("SELECT COUNT(*) c FROM messages WHERE status='new'").fetchone()["c"]
    out({"unprocessed_total": left, "messages": msgs})


def cmd_skip(a):
    conn = db()
    for mid in a.ids:
        conn.execute("UPDATE messages SET status='skipped' WHERE id=?", (mid,))
    log(conn, a.by, "skip", f"skipped messages {a.ids} ({a.reason})")
    conn.commit()
    print(f"skipped {len(a.ids)} message(s)")


def cmd_replay(a):
    """Stream a scenario's SMS feed into the inbox, like an SMS gateway would."""
    conn = db()
    path = SCENARIO_DIR / scenario_name(conn) / "feed.jsonl"
    feed = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Replaying {len(feed)} messages from {path.name} at {a.speed}x speed. Ctrl+C to stop.")
    start = time.time()
    for item in feed:
        wait = item["t"] / a.speed - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        conn.execute(
            "INSERT INTO messages(source, sender, text, received_at) VALUES (?,?,?,?)",
            (item.get("source", "sms"), item["sender"], item["text"], now()),
        )
        log(conn, item.get("source", "sms"), "message", f"{item['sender']}: {item['text'][:90]}")
        conn.commit()
        print(f"[{item['t']:>4}s] {item['sender']}: {item['text'][:70]}")
    print("Replay finished.")


# --------------------------------------------------------------------------- places

def cmd_geo(a):
    conn = db()
    places = gazetteer(conn)
    q = a.query.lower()
    hits = [{"place": k, **v} for k, v in places.items() if q in k.lower() or any(q in al.lower() for al in v.get("aliases", []))]
    if not hits:
        close = difflib.get_close_matches(q, [k.lower() for k in places], n=3, cutoff=0.5)
        hits = [{"place": k, **v} for k, v in places.items() if k.lower() in close]
    out(hits or {"result": "unknown place", "known_places": sorted(places)})


# --------------------------------------------------------------------------- cases

def _add_case(conn, c: dict, by: str) -> int:
    places = gazetteer(conn)
    lat, lon = c.get("lat"), c.get("lon")
    if (lat is None or lon is None) and c.get("place"):
        for name, v in places.items():
            names = [name.lower()] + [al.lower() for al in v.get("aliases", [])]
            if c["place"].lower() in names:
                lat, lon = v["lat"], v["lon"]
                break
    if lat is None or lon is None:
        raise ValueError(f"no coordinates for place '{c.get('place')}'. Run: python relief.py geo \"<name>\"")
    urgency = int(c.get("urgency", 3))
    if not 1 <= urgency <= 5:
        raise ValueError("urgency must be 1-5")
    ts = now()
    cur = conn.execute(
        """INSERT INTO cases(place, lat, lon, people, needs, urgency, lang, summary, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (c.get("place"), lat, lon, int(c.get("people", 0)), c.get("needs", ""), urgency,
         c.get("lang", ""), c.get("summary", ""), ts, ts),
    )
    cid = cur.lastrowid
    for mid in c.get("message_ids", []):
        conn.execute("UPDATE messages SET status='processed', case_id=? WHERE id=?", (cid, mid))
    log(conn, by, "case", f"Case #{cid} {URGENCY_WORDS[urgency]} at {c.get('place')}: {c.get('summary', '')[:80]}")
    return cid


def cmd_case_add(a):
    conn = db()
    try:
        cid = _add_case(conn, {
            "place": a.place, "lat": a.lat, "lon": a.lon, "people": a.people, "needs": a.needs,
            "urgency": a.urgency, "lang": a.lang, "summary": a.summary, "message_ids": a.msg or [],
        }, a.by)
    except ValueError as e:
        die(str(e))
    conn.commit()
    print(f"case #{cid} created")


def cmd_case_add_batch(a):
    raw = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"invalid JSON: {e}")
    conn = db()
    made, failed = [], []
    for c in items:
        try:
            made.append(_add_case(conn, c, a.by))
        except (ValueError, KeyError) as e:
            failed.append({"case": c.get("summary", c), "error": str(e)})
    conn.commit()
    out({"created": made, "failed": failed})


def cmd_case_list(a):
    conn = db()
    q = "SELECT id, place, people, needs, urgency, status, reports, summary, zone FROM cases"
    args = []
    if a.status:
        q += " WHERE status=?"
        args.append(a.status)
    q += " ORDER BY urgency DESC, id"
    out(rows(conn.execute(q, args)))


def cmd_case_show(a):
    conn = db()
    c = conn.execute("SELECT * FROM cases WHERE id=?", (a.id,)).fetchone()
    if not c:
        die(f"no case #{a.id}")
    msgs = rows(conn.execute("SELECT id, sender, text FROM messages WHERE case_id=?", (a.id,)))
    disp = rows(conn.execute("SELECT * FROM dispatches WHERE case_id=?", (a.id,)))
    out({"case": dict(c), "messages": msgs, "dispatches": disp})


def cmd_case_update(a):
    conn = db()
    if not conn.execute("SELECT 1 FROM cases WHERE id=?", (a.id,)).fetchone():
        die(f"no case #{a.id}")
    sets, args = [], []
    for field in ("status", "urgency", "people", "needs", "note"):
        val = getattr(a, field)
        if val is not None:
            sets.append(f"{field}=?")
            args.append(val)
    if not sets:
        die("nothing to update")
    sets.append("updated_at=?")
    args += [now(), a.id]
    conn.execute(f"UPDATE cases SET {', '.join(sets)} WHERE id=?", args)
    if a.status in ("rescued", "closed"):
        conn.execute("UPDATE resources SET status='available', case_id=NULL WHERE case_id=?", (a.id,))
        conn.execute("UPDATE dispatches SET status='done', updated_at=? WHERE case_id=? AND status='sent'", (now(), a.id))
    log(conn, a.by, "update", f"Case #{a.id} updated: " + ", ".join(s.split("=")[0] for s in sets[:-1]) + (f" -> {a.status}" if a.status else ""))
    conn.commit()
    print(f"case #{a.id} updated")


# --------------------------------------------------------------------------- verify

def cmd_dupes(a):
    """Suggest likely duplicate cases: close together and similar wording."""
    conn = db()
    cs = rows(conn.execute("SELECT id, place, lat, lon, people, summary FROM cases WHERE status IN ('open','verifying')"))
    pairs = []
    for i, x in enumerate(cs):
        for y in cs[i + 1:]:
            dist = km(x["lat"], x["lon"], y["lat"], y["lon"])
            if dist > a.radius:
                continue
            sim = difflib.SequenceMatcher(None, x["summary"].lower(), y["summary"].lower()).ratio()
            same_people = x["people"] and x["people"] == y["people"]
            score = round(sim + (0.25 if same_people else 0) + (0.2 if dist < 0.3 else 0), 2)
            if score >= a.threshold:
                pairs.append({"case_a": x["id"], "case_b": y["id"], "km_apart": round(dist, 2),
                              "text_similarity": round(sim, 2), "score": score,
                              "a": x["summary"], "b": y["summary"]})
    pairs.sort(key=lambda p: -p["score"])
    out({"candidates": pairs, "hint": "Check each pair. Merge true duplicates with: case merge KEEP DUP"})


def cmd_case_merge(a):
    conn = db()
    keep = conn.execute("SELECT * FROM cases WHERE id=?", (a.keep,)).fetchone()
    dup = conn.execute("SELECT * FROM cases WHERE id=?", (a.dup,)).fetchone()
    if not keep or not dup:
        die("both cases must exist")
    conn.execute("UPDATE cases SET status='duplicate', dup_of=?, updated_at=? WHERE id=?", (a.keep, now(), a.dup))
    conn.execute("UPDATE cases SET reports=reports+?, urgency=MAX(urgency, ?), updated_at=? WHERE id=?",
                 (dup["reports"], dup["urgency"], now(), a.keep))
    conn.execute("UPDATE messages SET case_id=? WHERE case_id=?", (a.keep, a.dup))
    log(conn, a.by, "merge", f"Case #{a.dup} is a duplicate of #{a.keep} (now {keep['reports'] + dup['reports']} reports)")
    conn.commit()
    print(f"case #{a.dup} merged into #{a.keep}")


def cmd_claim(a):
    """Record a verdict on a claim (e.g. 'Third Mainland Bridge collapsed')."""
    conn = db()
    conn.execute("INSERT INTO claims(topic, verdict, reason, created_at) VALUES (?,?,?,?)",
                 (a.topic, a.verdict, a.reason, now()))
    for cid in a.cases or []:
        status = "rumour" if a.verdict == "false" else "open"
        conn.execute("UPDATE cases SET status=?, note=?, updated_at=? WHERE id=?", (status, a.reason, now(), cid))
    icon = {"false": "RUMOUR BLOCKED", "true": "CONFIRMED", "unclear": "UNCLEAR"}[a.verdict]
    log(conn, a.by, "claim", f"{icon}: {a.topic}. {a.reason}")
    conn.commit()
    print(f"claim recorded: {a.topic} -> {a.verdict}")


# --------------------------------------------------------------------------- dispatch

def cmd_resources(a):
    conn = db()
    q = "SELECT * FROM resources" + (" WHERE status='available'" if a.available else "") + " ORDER BY kind, id"
    out(rows(conn.execute(q)))


def cmd_match(a):
    """Rank available resources for a case by distance and fit."""
    conn = db()
    c = conn.execute("SELECT * FROM cases WHERE id=?", (a.case,)).fetchone()
    if not c:
        die(f"no case #{a.case}")
    res = rows(conn.execute("SELECT * FROM resources WHERE status='available'"))
    needs = (c["needs"] or "").lower()
    ranked = []
    for r in res:
        d = km(c["lat"], c["lon"], r["lat"], r["lon"])
        fit = 0
        if r["kind"] == "boat" and any(w in needs for w in ("rescue", "trapped", "roof", "water", "evacuat", "boat")):
            fit = 2
        elif r["kind"] == "medical" and any(w in needs for w in ("medic", "injur", "sick", "pregnan", "insulin", "bleed", "doctor")):
            fit = 2
        elif r["kind"] == "supplies" and any(w in needs for w in ("food", "water", "supplies", "blanket", "shelter")):
            fit = 2
        eta = round(d / (18 if r["kind"] == "boat" else 25) * 60) + 5
        ranked.append({"resource": r["id"], "kind": r["kind"], "name": r["name"], "km": round(d, 1),
                       "eta_min": eta, "capacity": r["capacity"], "fit": fit})
    ranked.sort(key=lambda x: (-x["fit"], x["km"]))
    out({"case": dict(c), "options": ranked[:5]})


def cmd_dispatch_propose(a):
    conn = db()
    c = conn.execute("SELECT * FROM cases WHERE id=?", (a.case,)).fetchone()
    r = conn.execute("SELECT * FROM resources WHERE id=?", (a.resource,)).fetchone()
    if not c or not r:
        die("case and resource must exist")
    if c["status"] in ("rumour", "duplicate", "rescued", "closed"):
        die(f"case #{a.case} is {c['status']}; it cannot be dispatched")
    if r["status"] != "available":
        die(f"{a.resource} is busy")
    eta = a.eta or round(km(c["lat"], c["lon"], r["lat"], r["lon"]) / 18 * 60) + 5
    ts = now()
    cur = conn.execute(
        "INSERT INTO dispatches(case_id, resource_id, eta_min, status, proposed_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (a.case, a.resource, eta, "proposed", a.by, ts, ts),
    )
    log(conn, a.by, "propose", f"Proposed {r['name']} -> case #{a.case} ({c['place']}), ETA {eta} min. Waiting for HQ approval.")
    conn.commit()
    print(f"dispatch #{cur.lastrowid} proposed (needs HQ approval: dispatch send {cur.lastrowid} --approved-by NAME)")


def cmd_dispatch_send(a):
    """Commit a dispatch. Agents are configured so this command needs a human 'Allow' in the Switch room."""
    conn = db()
    d = conn.execute("SELECT * FROM dispatches WHERE id=?", (a.id,)).fetchone()
    if not d:
        die(f"no dispatch #{a.id}")
    if d["status"] != "proposed":
        die(f"dispatch #{a.id} is already {d['status']}")
    r = conn.execute("SELECT * FROM resources WHERE id=?", (d["resource_id"],)).fetchone()
    if r["status"] != "available":
        die(f"{r['id']} was taken by another dispatch")
    ts = now()
    conn.execute("UPDATE dispatches SET status='sent', approved_by=?, updated_at=? WHERE id=?", (a.approved_by, ts, a.id))
    conn.execute("UPDATE resources SET status='assigned', case_id=? WHERE id=?", (d["case_id"], d["resource_id"]))
    conn.execute("UPDATE cases SET status='dispatched', updated_at=? WHERE id=?", (ts, d["case_id"]))
    log(conn, a.by, "dispatch", f"SENT {r['name']} -> case #{d['case_id']}, ETA {d['eta_min']} min. Approved by {a.approved_by}.")
    conn.commit()
    print(f"dispatch #{a.id} sent: {r['name']} -> case #{d['case_id']} (approved by {a.approved_by})")


def cmd_dispatch_cancel(a):
    conn = db()
    d = conn.execute("SELECT * FROM dispatches WHERE id=?", (a.id,)).fetchone()
    if not d:
        die(f"no dispatch #{a.id}")
    conn.execute("UPDATE dispatches SET status='cancelled', updated_at=? WHERE id=?", (now(), a.id))
    if d["status"] == "sent":
        conn.execute("UPDATE resources SET status='available', case_id=NULL WHERE id=?", (d["resource_id"],))
        conn.execute("UPDATE cases SET status='open', updated_at=? WHERE id=?", (now(), d["case_id"]))
    log(conn, a.by, "cancel", f"Dispatch #{a.id} cancelled: {a.reason}")
    conn.commit()
    print(f"dispatch #{a.id} cancelled")


def cmd_dispatch_list(a):
    conn = db()
    out(rows(conn.execute(
        """SELECT d.id, d.case_id, c.place, d.resource_id, d.eta_min, d.status, d.proposed_by, d.approved_by
           FROM dispatches d JOIN cases c ON c.id=d.case_id ORDER BY d.id DESC""")))


# --------------------------------------------------------------------------- zones and sitrep

def cmd_zones(a):
    """Find hotspots: clusters of active cases not yet covered by a zone room."""
    conn = db()
    cs = rows(conn.execute("SELECT id, place, lat, lon, urgency FROM cases WHERE status IN ('open','verifying','dispatched')"))
    zones = rows(conn.execute("SELECT * FROM zones"))
    uncovered = [c for c in cs if not any(km(c["lat"], c["lon"], z["lat"], z["lon"]) <= z["radius_km"] for z in zones)]
    hotspots, used = [], set()
    for c in sorted(uncovered, key=lambda x: -x["urgency"]):
        if c["id"] in used:
            continue
        group = [o for o in uncovered if o["id"] not in used and km(c["lat"], c["lon"], o["lat"], o["lon"]) <= a.radius]
        if len(group) >= a.min_cases:
            used.update(o["id"] for o in group)
            lat = sum(o["lat"] for o in group) / len(group)
            lon = sum(o["lon"] for o in group) / len(group)
            hotspots.append({"suggested_zone": c["place"].lower().replace(" ", "-"), "lat": round(lat, 4),
                             "lon": round(lon, 4), "cases": [o["id"] for o in group],
                             "critical": sum(1 for o in group if o["urgency"] >= 5)})
    out({"existing_zones": zones, "new_hotspots": hotspots})


def cmd_zone_add(a):
    conn = db()
    conn.execute("INSERT OR REPLACE INTO zones VALUES (?,?,?,?,?,?)", (a.name, a.lat, a.lon, a.radius, a.room, now()))
    for c in rows(conn.execute("SELECT id, lat, lon FROM cases")):
        if km(c["lat"], c["lon"], a.lat, a.lon) <= a.radius:
            conn.execute("UPDATE cases SET zone=? WHERE id=?", (a.name, c["id"]))
    log(conn, a.by, "zone", f"New zone '{a.name}' opened with its own room {a.room}")
    conn.commit()
    print(f"zone {a.name} registered")


def stats(conn) -> dict:
    c = lambda q, *p: conn.execute(q, p).fetchone()[0]
    return {
        "messages_in": c("SELECT COUNT(*) FROM messages"),
        "messages_waiting": c("SELECT COUNT(*) FROM messages WHERE status='new'"),
        "cases_active": c("SELECT COUNT(*) FROM cases WHERE status IN ('open','verifying','dispatched')"),
        "critical_open": c("SELECT COUNT(*) FROM cases WHERE status IN ('open','verifying') AND urgency>=5"),
        "dispatched": c("SELECT COUNT(*) FROM cases WHERE status='dispatched'"),
        "rescued": c("SELECT COUNT(*) FROM cases WHERE status='rescued'"),
        "people_rescued": c("SELECT COALESCE(SUM(people),0) FROM cases WHERE status='rescued'"),
        "people_waiting": c("SELECT COALESCE(SUM(people),0) FROM cases WHERE status IN ('open','verifying','dispatched')"),
        "duplicates_merged": c("SELECT COUNT(*) FROM cases WHERE status='duplicate'"),
        "rumours_blocked": c("SELECT COUNT(*) FROM claims WHERE verdict='false'"),
        "resources_free": c("SELECT COUNT(*) FROM resources WHERE status='available'"),
        "resources_total": c("SELECT COUNT(*) FROM resources"),
    }


def cmd_sitrep(a):
    conn = db()
    s = stats(conn)
    top = rows(conn.execute(
        "SELECT id, place, people, needs FROM cases WHERE status IN ('open','verifying') ORDER BY urgency DESC, id LIMIT 5"))
    out({"at": now(), "stats": s, "top_open_cases": top,
         "recent_claims": rows(conn.execute("SELECT topic, verdict, reason FROM claims ORDER BY id DESC LIMIT 3"))})


def cmd_log(a):
    conn = db()
    out(rows(conn.execute("SELECT at, actor, kind, text FROM events ORDER BY id DESC LIMIT ?", (a.limit,))))


# --------------------------------------------------------------------------- map server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            conn = db()
            state = {
                "scenario": scenario_name(conn),
                "stats": stats(conn),
                "cases": rows(conn.execute("SELECT * FROM cases WHERE status != 'duplicate'")),
                "resources": rows(conn.execute("SELECT * FROM resources")),
                "dispatches": rows(conn.execute("SELECT * FROM dispatches WHERE status IN ('proposed','sent')")),
                "zones": rows(conn.execute("SELECT * FROM zones")),
                "events": rows(conn.execute("SELECT at, actor, kind, text FROM events ORDER BY id DESC LIMIT 25")),
            }
            conn.close()
            self._send(200, json.dumps(state).encode(), "application/json")
            return
        name = "map.html" if self.path in ("/", "/index.html") else self.path.lstrip("/").split("?")[0]
        f = (WEB_DIR / name).resolve()
        if WEB_DIR.resolve() not in f.parents or not f.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css", "svg": "image/svg+xml"}.get(f.suffix[1:], "application/octet-stream")
        self._send(200, f.read_bytes(), ctype + "; charset=utf-8")


def cmd_serve(a):
    db().close()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Relief map live at http://127.0.0.1:{a.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(prog="relief", description="Relief Room crisis board")
    p.add_argument("--by", default=os.environ.get("RELIEF_AGENT", "human"), help="who is acting (agent name)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="reset the board and load a scenario")
    s.add_argument("--scenario", default="lagos-flood")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("ingest", help="store one incoming message (e.g. from Telegram)")
    s.add_argument("--source", default="telegram")
    s.add_argument("--sender", required=True)
    s.add_argument("text")
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("inbox", help="unprocessed messages")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("skip", help="mark messages as not actionable")
    s.add_argument("ids", type=int, nargs="+")
    s.add_argument("--reason", default="not actionable")
    s.set_defaults(fn=cmd_skip)

    s = sub.add_parser("replay", help="stream the scenario SMS feed into the inbox")
    s.add_argument("--speed", type=float, default=1.0)
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("geo", help="look up a place name")
    s.add_argument("query")
    s.set_defaults(fn=cmd_geo)

    case = sub.add_parser("case", help="case commands").add_subparsers(dest="sub", required=True)
    s = case.add_parser("add")
    s.add_argument("--place", required=True)
    s.add_argument("--lat", type=float)
    s.add_argument("--lon", type=float)
    s.add_argument("--people", type=int, default=0)
    s.add_argument("--needs", default="")
    s.add_argument("--urgency", type=int, default=3)
    s.add_argument("--lang", default="")
    s.add_argument("--summary", default="")
    s.add_argument("--msg", type=int, nargs="*")
    s.set_defaults(fn=cmd_case_add)
    s = case.add_parser("add-batch", help="create many cases from a JSON array (stdin with -)")
    s.add_argument("file", nargs="?", default="-")
    s.set_defaults(fn=cmd_case_add_batch)
    s = case.add_parser("list")
    s.add_argument("--status", choices=CASE_STATUSES)
    s.set_defaults(fn=cmd_case_list)
    s = case.add_parser("show")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_case_show)
    s = case.add_parser("update")
    s.add_argument("id", type=int)
    s.add_argument("--status", choices=CASE_STATUSES)
    s.add_argument("--urgency", type=int)
    s.add_argument("--people", type=int)
    s.add_argument("--needs")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_case_update)
    s = case.add_parser("merge", help="mark DUP as a duplicate of KEEP")
    s.add_argument("keep", type=int)
    s.add_argument("dup", type=int)
    s.set_defaults(fn=cmd_case_merge)

    s = sub.add_parser("dupes", help="suggest duplicate cases")
    s.add_argument("--radius", type=float, default=1.0)
    s.add_argument("--threshold", type=float, default=0.55)
    s.set_defaults(fn=cmd_dupes)

    s = sub.add_parser("claim", help="record a verdict on a rumour or claim")
    s.add_argument("topic")
    s.add_argument("--verdict", choices=["true", "false", "unclear"], required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--cases", type=int, nargs="*")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("resources", help="boats, medics, supplies")
    s.add_argument("--available", action="store_true")
    s.set_defaults(fn=cmd_resources)

    s = sub.add_parser("match", help="rank resources for a case")
    s.add_argument("case", type=int)
    s.set_defaults(fn=cmd_match)

    disp = sub.add_parser("dispatch", help="dispatch commands").add_subparsers(dest="sub", required=True)
    s = disp.add_parser("propose")
    s.add_argument("case", type=int)
    s.add_argument("resource")
    s.add_argument("--eta", type=int)
    s.set_defaults(fn=cmd_dispatch_propose)
    s = disp.add_parser("send", help="commit a proposed dispatch (needs human approval in the room)")
    s.add_argument("id", type=int)
    s.add_argument("--approved-by", required=True)
    s.set_defaults(fn=cmd_dispatch_send)
    s = disp.add_parser("cancel")
    s.add_argument("id", type=int)
    s.add_argument("--reason", default="cancelled")
    s.set_defaults(fn=cmd_dispatch_cancel)
    s = disp.add_parser("list")
    s.set_defaults(fn=cmd_dispatch_list)

    s = sub.add_parser("zones", help="find hotspots that need their own room")
    s.add_argument("--radius", type=float, default=2.5)
    s.add_argument("--min-cases", type=int, default=3)
    s.set_defaults(fn=cmd_zones)
    s = sub.add_parser("zone-add", help="register a zone room")
    s.add_argument("name")
    s.add_argument("--lat", type=float, required=True)
    s.add_argument("--lon", type=float, required=True)
    s.add_argument("--radius", type=float, default=2.5)
    s.add_argument("--room", required=True)
    s.set_defaults(fn=cmd_zone_add)

    s = sub.add_parser("sitrep", help="situation report data")
    s.set_defaults(fn=cmd_sitrep)
    s = sub.add_parser("log", help="recent activity")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_log)
    s = sub.add_parser("serve", help="run the live map")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
