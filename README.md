# 🛟 Flare

**An AI crisis control room for disaster response, built on [Switch](https://github.com/sandbox-quantum/switch).**

When a city floods, help requests arrive as thousands of messy messages on SMS, WhatsApp and Telegram, in
several languages. The same family gets reported five times, a rumour sends boats to the wrong place, and the
real SOS gets lost. Flare puts **field volunteers (Telegram)**, **HQ coordinators (Mattermost / Slack)**
and **five AI agents** in one Switch workspace. The agents turn the noise into a verified, prioritised rescue
board, and **a named human approves every dispatch**.

> Flip the Switch Hackathon · **Track 01: Best Business Workflow**
> **Live demo (a recorded run, plays in your browser): https://jennivarl.github.io/flare/**
> Scenario data is simulated (fictional people, real Lagos geography).

---

## The problem (real, documented)

- In Haiti, first responders received **over 5,000 SMS messages per hour** asking for help ([ITU](https://www.itu.int/net/epub/TSB/2025-AI-for-Good-Innovate-for-Impact/files/basic-html/page286.html)).
- Flood volunteers coordinate on WhatsApp, Telegram and shared spreadsheets; **rumours slip through and false alarms
  spark "phantom deployments"** ([Everhem](https://development.everhem.com/digital-lifeline-outran-flood)).
- WhatsApp is now real dispatch infrastructure for volunteer emergency services ([ISCRAM](https://ojs.iscram.org/index.php/Proceedings/article/view/222)),
  and responders insist AI must support people, not replace them ([Rest of World](https://restofworld.org/2026/venezuela-ai-citizen-disaster-response/)).

**Who it is for:** emergency management agencies, NGOs, Red Cross / Red Crescent chapters, and community
response groups that already coordinate in chat.

---

## How it works

```mermaid
flowchart LR
  subgraph Field["Field room (Telegram)"]
    V[Volunteers and people in danger]
  end
  SMS[(SMS gateway feed)] --> IN
  V -- every message --> IN[@intake]
  subgraph HQ["HQ room (Mattermost / Slack)"]
    IN --> VE[@verify]
    VE -- ready cases --> D["@dispatcher role (exclusive)"]
    D -- "propose: Boat 2 -> case #7" --> H[HQ coordinator]
    H -- "Allow (recorded by name)" --> D
    S[@sitrep]
    SB[@standby]
  end
  D -. "if dispatcher dies, role is freed" .-> SB
  S -- "new hotspot" --> Z["zone-* room created on the fly"]
  IN & VE & D & S --> B[(Relief board: relief.py + SQLite)]
  B --> M[Live map :8787]
```

| Agent | What it does |
|---|---|
| **@intake** | Reads every message (Pidgin, Yoruba, English…), creates clean cases with place, people, needs and urgency. Skips scams. |
| **@verify** | Merges duplicate reports of the same family, checks big claims against eyewitnesses, and **blocks rumours** so they can't be dispatched. |
| **@dispatcher** (role) | Matches verified cases to the nearest fitting boat, medical team or supply truck. Only *proposes*. |
| **@standby** | Backup dispatcher. Takes over the exclusive `dispatcher` role if the main one goes down. |
| **@sitrep** | Posts situation reports for HQ and a safe public version for the field, and opens a new **zone room** when a hotspot appears. |

### The three moments in the demo

1. **Noise to map.** 22 messages arrive in mixed languages, and the live map fills with prioritised cases.
2. **Rumour blocked.** Four people say "Third Mainland Bridge collapsed". Two eyewitnesses *on* the bridge say it
   stands. @verify blocks the rumour, and no boat is wasted.
3. **The dispatcher dies, nothing is dropped.** We stop the dispatch agent mid-crisis. Switch frees the exclusive
   `dispatcher` role, @standby takes it, and it continues from the exact proposals left waiting.

---

## Why Switch is central (it does not work without it)

| Switch feature | How Flare uses it |
|---|---|
| **Cross-platform bridge** | Field volunteers stay on Telegram (cheap phones, low data); HQ works in Mattermost / Slack. One workspace. |
| **Many agents, one room, shared context** | Five agents share room Instructions and one board, and hand off by mention (`@verify` → `@dispatcher`). |
| **Exclusive roles** | `dispatcher` has exactly one holder, so two agents can never send the same boat. When the holder dies the lease is released and **@standby takes over**. |
| **Approvals recorded by name** | `dispatch send` is configured as an *ask* permission, so every dispatch shows **Allow / Decline** in the room and Switch records which human approved it. |
| **"Who can talk to your agent" rules** | The public can reach **@intake only**. Only HQ people can instruct the dispatcher, so a random sender cannot launch a boat. |
| **Rooms created by agents** | @sitrep opens a `zone-<area>` room for a new hotspot and links it to HQ. |
| **Main agent in a room** | In the Telegram field room, `!assign-agent @intake` makes every message reach intake without an @mention. |

Without Switch you would need a separate bot per platform, your own access control, your own approval UI, and
your own failover. With Switch they are room settings.

---

## How to Test

### Part A: test the relief board on its own (2 minutes, no Switch needed)

This proves the engine works before you connect any chat app.

**You need:** Python 3.10 or newer (`python --version`). No packages to install.

1. Get the code:
   ```bash
   git clone https://github.com/Jennivarl/flare.git
   cd flare
   ```
2. Start a fresh board with the Lagos flood scenario:
   ```bash
   python relief.py init
   ```
   ✅ You should see `Relief board ready (lagos-flood)`.
3. Open the live map. In a **second terminal**:
   ```bash
   python relief.py serve
   ```
   Then open **http://127.0.0.1:8787** in your browser. ✅ You see a dark map of Lagos with 8 rescue resources (🚤 🩺 🚚).
4. Play the flood. Back in the first terminal:
   ```bash
   python relief.py replay --speed 5
   ```
   ✅ 22 messages stream in. The "Messages in" counter rises to 22.
5. Act like the agents would (copy and paste):
   ```bash
   python relief.py --by intake case add --place Makoko --people 4 --urgency 5 --needs "rescue from roof" --summary "Mother and 3 children on roof, baby sick" --msg 1
   python relief.py --by intake case add --place "makoko community" --people 4 --urgency 5 --needs "rescue from roof" --summary "Mama Bisi and 3 kids on roof by church, baby sick" --msg 4
   python relief.py --by intake case add --place "Third Mainland Bridge" --urgency 5 --needs boats --summary "Report: bridge collapsed" --msg 2
   python relief.py dupes
   python relief.py --by verify case merge 1 2
   python relief.py --by verify claim "Third Mainland Bridge collapsed" --verdict false --reason "2 eyewitnesses on the bridge say it stands" --cases 3
   python relief.py match 1
   python relief.py --by dispatch dispatch propose 1 boat-1
   python relief.py --by dispatch dispatch send 1 --approved-by "Your Name"
   python relief.py --by dispatch case update 1 --status rescued
   python relief.py sitrep
   ```
   ✅ On the map: a red pulsing case appears in Makoko, the duplicate disappears, the bridge case turns **purple**
   (rumour), a green line shows Rescue Boat 1 en route, then the case turns **green** (rescued).
   `sitrep` shows `people_rescued: 4`, `duplicates_merged: 1`, `rumours_blocked: 1`.

### Part B: run the full workflow in Switch (about 20 minutes)

**You need:**
- [Switch Console](https://docs.switchagents.ai/switch-rooms/getting-started) (macOS, Windows or Linux; Windows and Linux are early access)
- Docker Desktop, running (Switch uses it for the bundled Mattermost)
- Claude Code installed and signed in (`claude --version`)
- Optional: a Telegram bot token from [@BotFather](https://t.me/BotFather) for the field room

**Steps:**
1. Follow the Switch quickstart until one agent answers you in a Mattermost channel.
2. Create a channel **`relief-hq`** and add it as a Switch room. Paste [`switch/room-instructions.md`](switch/room-instructions.md)
   into the room's **Instructions**.
3. In Switch Console, create five agents with the **Claude Code** provider. For each one, set **Directory** to the
   matching folder and keep **Bypass permissions OFF**:

   | Agent name | Directory | Who can talk to it |
   |---|---|---|
   | `intake` | `flare/agents/intake` | Anyone |
   | `verify` | `flare/agents/verify` | Me and my agents |
   | `dispatch` | `flare/agents/dispatch` | Custom rules: HQ people only |
   | `standby` | `flare/agents/standby` | Custom rules: HQ people only |
   | `sitrep` | `flare/agents/sitrep` | Me and my agents |

   Each folder has a `CLAUDE.md` (the agent's job) and a `.claude/settings.json` (its permissions; dispatch and
   standby must ask before `dispatch send`).
4. In `relief-hq`, invite them: `!invite-agent @intake`, `!invite-agent @verify`, `!invite-agent @dispatch`,
   `!invite-agent @standby`, `!invite-agent @sitrep`. Check with `!list-agents`.
5. Create an exclusive role named **`dispatcher`** ("Dispatcher: matches verified cases to resources") and ask
   `@dispatch take the dispatcher role`. Check with `!roles`.
6. Optional field room: connect Telegram in Switch Console, add your bot to a Telegram group, invite `@intake`
   there and run `!assign-agent @intake` so every message reaches it.
7. Start the board and map from the `flare` folder:
   ```bash
   python relief.py init
   python relief.py serve        # keep open, then open http://127.0.0.1:8787
   python relief.py replay --speed 3   # in another terminal
   ```
8. Run the crisis in the room:
   - `@intake triage the inbox` → ✅ cases appear on the map, intake posts a summary.
   - `@verify check duplicates and claims` → ✅ the Makoko family is merged and the bridge rumour turns purple.
   - `@dispatcher dispatch the critical cases` → ✅ it proposes boats and medics and asks HQ.
   - Reply `yes` and press **Allow once** on the prompt → ✅ green route lines appear; the map shows who approved.
   - Stop the `dispatch` agent in Switch Console, then: `@standby the dispatcher is down, take over` →
     ✅ `!roles` shows standby holding `dispatcher`, and it continues from the waiting proposals.
   - `@sitrep sitrep` → ✅ a situation report with real numbers; it opens a `zone-*` room if a hotspot formed.
   - From Telegram (or the room): `Case 1 rescued, all 4 safe` then `@dispatcher update` → ✅ the case turns green.

**Troubleshooting**
- Map empty? Make sure `serve` and the agents use the same folder (the board lives in `flare/data/relief.db`).
- Agent says it is not available? Switch Console must stay open: agents answer only while their session runs.
- `unknown place`? Run `python relief.py geo "<name>"` to see the known places for the scenario.

---

## Judging criteria, mapped

- **Use of Switch:** cross-platform rooms, five agents, an exclusive role with failover, named approvals, access
  rules, and rooms created by agents. Remove Switch and the workflow falls apart (see the table above).
- **Technical execution:** zero-dependency Python board (SQLite, standard library only), a live map, a
  reproducible scenario, and per-agent permissions in code. Part A of How to Test runs in 2 minutes.
- **Creativity and impact:** crisis response is a real, documented problem where chat is already the
  infrastructure. Flare adds verification and accountability, not just speed.
- **Presentation:** a 3-minute video showing the room, the map and the failover live.

## Project layout

```
relief.py                  the relief board: CLI + live map server (standard library only)
web/map.html               live operations map (Leaflet)
scenarios/lagos-flood/     simulated SMS feed, places, rescue resources
agents/<name>/CLAUDE.md    each agent's job
agents/<name>/.claude/     each agent's permissions (dispatch send = ask)
switch/room-instructions.md  room Instructions for Switch
```

## Safety notes

- The scenario is simulated. All people, phone numbers and messages are fictional.
- AI agents never dispatch on their own: every dispatch needs a named human approval.
- Public field rooms never receive names, phone numbers or exact addresses.

## License

MIT
