#!/usr/bin/env python3
"""Record a playback of the Lagos flood scenario for the public demo page (docs/).

Runs the real relief board through the same steps the agents take in the Switch room,
and saves a snapshot after each step. The demo page plays these snapshots in a loop.

    python tools/record_demo.py      ->  docs/demo.json
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["RELIEF_DB"] = str(Path(tempfile.mkdtemp()) / "demo.db")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import relief  # noqa: E402

frames = []


def run(*args):
    relief.main(list(args))


def snap(caption):
    conn = relief.db()
    state = relief.board_state(conn)
    conn.close()
    state["caption"] = caption
    frames.append(state)


feed = [json.loads(l) for l in (ROOT / "scenarios/lagos-flood/feed.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def ingest(items):
    for m in items:
        run("ingest", "--source", m.get("source", "sms"), "--sender", m["sender"], m["text"])


def cases(by, items):
    conn = relief.db()
    for c in items:
        relief._add_case(conn, c, by)
    conn.commit()
    conn.close()


run("init")
snap("Flood alert. The Flare room is live: HQ in Mattermost, volunteers on Telegram, agents ready.")

ingest(feed[:8])
snap("8 messages arrive in Pidgin, Yoruba and English. Some are duplicates, one is a scam, one is a rumour.")

cases("intake", [
    {"place": "Makoko", "people": 4, "needs": "rescue from roof, sick baby", "urgency": 5, "lang": "pcm", "summary": "Mother and 3 children on roof near blue church, baby sick", "message_ids": [1]},
    {"place": "Third Mainland Bridge", "people": 0, "needs": "boats", "urgency": 5, "lang": "en", "summary": "Report: Third Mainland Bridge collapsed, cars in water", "message_ids": [2]},
    {"place": "Ilaje Bariga", "people": 6, "needs": "rescue, elder cannot walk", "urgency": 4, "lang": "yo", "summary": "Water inside home, 6 people, elderly woman cannot walk", "message_ids": [3]},
    {"place": "Makoko", "people": 4, "needs": "rescue from roof, sick baby", "urgency": 5, "lang": "en", "summary": "Mama Bisi and 3 kids on roof in Makoko by the church, baby sick", "message_ids": [4]},
])
run("--by", "intake", "skip", "5", "--reason", "scam asking for BVN")
snap("@intake turns messages into cases, and skips a scam asking for bank details.")

cases("intake", [
    {"place": "Third Mainland Bridge", "people": 0, "needs": "boats", "urgency": 5, "lang": "pcm", "summary": "Report: bridge fell, seen on WhatsApp video", "message_ids": [6]},
    {"place": "Oworonshoki", "people": 3, "needs": "medical, woman in labour", "urgency": 5, "lang": "en", "summary": "Pregnant woman in labour, road flooded, ambulance cannot reach", "message_ids": [7]},
    {"place": "Ebute Metta", "people": 40, "needs": "food and water", "urgency": 3, "lang": "en", "summary": "40 people in primary school, no food since yesterday", "message_ids": [8]},
])
snap("Critical cases light up the map. Two people say the Third Mainland Bridge collapsed.")

ingest(feed[8:16])
cases("intake", [
    {"place": "Third Mainland Bridge", "people": 0, "needs": "none", "urgency": 1, "lang": "en", "summary": "Eyewitness ON the bridge: not collapsed, only traffic", "message_ids": [9]},
    {"place": "Ilaje Bariga", "people": 1, "needs": "medical, insulin", "urgency": 5, "lang": "en", "summary": "Man (78) alone, ground floor flooded, needs insulin", "message_ids": [10]},
    {"place": "Makoko", "people": 4, "needs": "rescue from roof", "urgency": 5, "lang": "pcm", "summary": "Mama Bisi still on roof with her children", "message_ids": [11]},
    {"place": "Lekki Phase 1", "people": 9, "needs": "rescue, water rising", "urgency": 4, "lang": "en", "summary": "2 families (9 people) trapped upstairs, water rising", "message_ids": [13]},
    {"place": "Third Mainland Bridge", "people": 0, "needs": "none", "urgency": 1, "lang": "en", "summary": "Eyewitness driving across: bridge fine, police directing traffic", "message_ids": [14]},
    {"place": "Ajah", "people": 2, "needs": "rescue from water", "urgency": 5, "lang": "en", "summary": "Canoe capsized, 2 men in water holding a tree", "message_ids": [15]},
])
run("--by", "intake", "skip", "16", "--reason", "thank-you note")
snap("More messages. Now two eyewitnesses standing on the bridge say it is fine.")

run("--by", "verify", "case", "merge", "1", "4")
run("--by", "verify", "case", "merge", "1", "10")
snap("@verify finds the same Makoko family reported 3 times and merges the reports.")

run("--by", "verify", "claim", "Third Mainland Bridge collapsed", "--verdict", "false",
    "--reason", "2 eyewitnesses on the bridge say it stands; reports trace back to one WhatsApp video", "--cases", "2", "5", "8", "12")
snap("RUMOUR BLOCKED. No boats wasted on the bridge (phantom deployment avoided).")

run("--by", "dispatch", "dispatch", "propose", "1", "boat-1")
run("--by", "dispatch", "dispatch", "propose", "6", "med-1")
run("--by", "dispatch", "dispatch", "propose", "13", "boat-3")
snap("@dispatcher proposes boats and medics. Nothing moves until a human at HQ approves.")

run("--by", "dispatch", "dispatch", "send", "1", "--approved-by", "Valentine (HQ)")
run("--by", "dispatch", "dispatch", "send", "2", "--approved-by", "Valentine (HQ)")
snap("HQ presses Allow in the Switch room. Switch records who approved each dispatch.")

frames.append(json.loads(json.dumps(frames[-1])))
frames[-1]["events"].insert(0, {"at": frames[-1]["events"][0]["at"], "actor": "switch", "kind": "zone", "text": "@dispatch went offline. The exclusive 'dispatcher' role was released."})
frames[-1]["caption"] = "The dispatch agent goes down mid-crisis. Switch frees its exclusive 'dispatcher' role."

run("--by", "standby", "dispatch", "send", "3", "--approved-by", "Valentine (HQ)")
run("--by", "standby", "dispatch", "propose", "9", "med-2")
snap("@standby takes the dispatcher role and picks up the exact work left waiting. Nothing is dropped.")

ingest(feed[16:])
run("--by", "dispatch", "case", "update", "1", "--status", "rescued", "--note", "Field: mother and 3 children safe, baby to clinic")
run("--by", "standby", "case", "update", "13", "--status", "rescued", "--note", "Field: both men pulled out of the water")
snap("Field volunteers confirm on Telegram: rescued. The map turns green.")

run("--by", "standby", "dispatch", "send", "4", "--approved-by", "Valentine (HQ)")
run("--by", "standby", "case", "update", "6", "--status", "rescued", "--note", "Baby delivered, mother and child stable")
snap("Every decision is on the record: who reported, who verified, who approved, who rescued.")

out = ROOT / "docs" / "demo.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"frames": frames}, ensure_ascii=False), encoding="utf-8")
print(f"{len(frames)} frames -> {out}")
