# 🛟 Flare

**An AI crisis control room for disaster response, built on [Switch](https://github.com/sandbox-quantum/switch).**

When a city floods, help requests arrive as thousands of messy messages on SMS, WhatsApp and Telegram, in
several languages. The same family gets reported five times, a rumour sends boats to the wrong place, and the
real SOS gets lost. Flare puts **field volunteers (Telegram)**, **HQ coordinators (Mattermost / Slack)**
and **AI agents** in one Switch workspace. The agents turn the noise into a verified, prioritised rescue
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
3. **The dispatcher hands over, nothing is dropped.** dispatch releases the exclusive `dispatcher` role, @standby
   takes it immediately and continues from the exact work left waiting. While dispatch holds the role, Switch refuses
   standby, so two agents can never dispatch at once.

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

There are two parts. **Part A** checks the relief board on its own in about 2 minutes, with nothing to install.
**Part B** runs the real workflow: real Claude Code agents in a real Switch room in Mattermost. Every result
listed in Part B was observed in a real run on Windows 11 with Switch Console v0.40.1.

### Part A: the relief board on its own (about 2 minutes, no Switch needed)

**You need:** Python 3.10 or newer. Check with `python --version`. There are no packages to install.

1. Get the code:
   ```bash
   git clone https://github.com/Jennivarl/flare.git
   cd flare
   ```
2. Start a fresh board with the Lagos flood scenario:
   ```bash
   python relief.py init
   ```
   ✅ You see `Relief board ready (lagos-flood)`.
3. Start the live map in a **second terminal** (leave it running):
   ```bash
   python relief.py serve
   ```
   Open **http://127.0.0.1:8787**. ✅ You see a grey map of Lagos with 8 rescue resources labelled
   B1 to B4 (boats), M1 and M2 (medical teams), S1 and S2 (supply trucks).
4. Back in the first terminal, play the flood:
   ```bash
   python relief.py replay --speed 5
   ```
   ✅ 22 messages stream in, and `python relief.py inbox` shows them waiting.
5. Do by hand what the agents do (copy and paste the whole block):
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
   ✅ On the map, an orange (critical) dot appears in Makoko and the duplicate disappears. The bridge case
   turns **purple** (rumour), a green line shows Rescue Boat 1 on its way, and then the Makoko dot turns
   **green** (rescued). `sitrep` shows `people_rescued: 4`, `duplicates_merged: 1`, `rumours_blocked: 1`.

### Part B: the real workflow in Switch and Mattermost (about 25 minutes)

**You need:**
- **Switch Console** from the [Switch releases page](https://github.com/sandbox-quantum/switch/releases/latest)
  (macOS, Windows or Linux). Windows and Linux are early access.
- **Docker Desktop**, installed and running. Switch runs Mattermost in Docker.
- **Claude Code**, installed and signed in. Check with `claude --version`.
- **Node.js 20 or newer**, which Switch uses to start agents. Check with `node --version`.
- **Python 3.10 or newer**, and this repository cloned (Part A, step 1).

#### Step 1. Set up the Switch server
1. Open Switch Console and choose **On this computer**, then **Continue**. Wait until the sidebar shows
   **Local Switch server · Running** (about 1 minute). On Windows, a black terminal window opens: that is the
   server's database. Leave it open.
2. If switch-buddy greets you, click **Claude Code** next to "Already signed in".

#### Step 2. Turn on Mattermost
1. Go to **Admin** → under **SERVER · Local Switch server**, click **Status**.
2. In the **Mattermost** box, turn the switch **on**. ✅ After 1 to 3 minutes (the first time downloads about
   650 MB) it says *"Running. Team chat for your rooms, in Docker beside the server"*.

> **Windows: if the box says "The Docker CLI was not found on this system"** even though Docker is running,
> that is a Switch Console v0.40.1 bug: it picks Docker's extensionless `docker` script before `docker.exe`.
> Close Switch Console and start it again from PowerShell with the override Switch supports:
> ```powershell
> $env:DOCKER_PATH = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
> Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue   # only needed inside VS Code's terminal
> Start-Process "$env:LOCALAPPDATA\Programs\Switch Console\Switch Console.exe"
> ```
> The switch is now clickable. (`ELECTRON_RUN_AS_NODE` is set inside VS Code terminals and makes any Electron
> app close straight away.)

#### Step 3. Log in to Mattermost
1. Go to **Home** → **Messaging apps** → on the **Mattermost** row click **⋮** → **Sign-in details…**
2. Open the **Server** address it shows (for example `http://localhost:55339`) and log in with that username and
   password.
3. Back on **Home**, the Mattermost row shows your handle (for example `@user`). If it says **No account linked**,
   choose **Link my account…** and select **This is me**, so the agents recognise you.

#### Step 4. Create the four agents
Go to **Your Agents** → the **+** card, and create each agent with these settings:
- **Agent provider:** Claude Code. **Run location:** this computer.
- **Who can talk to your agent:** **Only me and my agents**. This is needed so the agents can hand work to each other.
- Leave **Auto mode** on and **Bypass permissions** off. Don't change **Advanced configuration**.

| Name | Directory (use your clone's full path) | Description |
|---|---|---|
| `intake` | `…/flare/agents/intake` | Turns emergency messages into cases |
| `verify` | `…/flare/agents/verify` | Merges duplicates and blocks rumours |
| `dispatch` | `…/flare/agents/dispatch` | Sends rescue resources after HQ approval |
| `standby` | `…/flare/agents/standby` | Backup dispatcher, takes over if dispatch goes down |

Each folder has a `CLAUDE.md` (the agent's job) and a `.claude/settings.json` (what it may run).
`dispatch send` is an **ask** rule for dispatch and standby, so Switch must get a human's approval before any
dispatch goes out.

**Shortcut:** ask switch-buddy in Switch Console to create all four from that table.

✅ Each agent's bot appears in Mattermost and says hello in Town Square.

#### Step 5. Create the flare-hq room
In Mattermost, **Town Square is not a Switch room**, so messages there don't reach the agents. In Mattermost,
adding an agent's bot to a channel is what creates a Switch room:
1. In Mattermost, click **+** → **Create new channel** → name it `flare-hq`.
2. Add the members **intake**, **verify**, **dispatch** and **standby** (channel menu → **Add members**).
3. In `flare-hq`, send:
   ```text
   !list-agents
   ```
   ✅ Switch replies with *"Agents in this room"* and lists all four with their descriptions.
4. Optional: paste [`switch/room-instructions.md`](switch/room-instructions.md) into the room's **Instructions**
   (Switch Console → **Your Rooms** → flare-hq → **Configuration**).

#### Step 6. Start the board and the map
In the `flare` folder:
```bash
python relief.py init
python relief.py serve
```
Keep `serve` running and open **http://127.0.0.1:8787**. In another terminal, stream the flood messages in:
```bash
python relief.py replay --speed 20
```
✅ It prints `Replay finished.`, and `python relief.py inbox` shows `"unprocessed_total": 22`.

#### Step 7. Run the crisis in flare-hq
Send each message in the `flare-hq` channel and wait for the agent to reply. The first time you address an agent,
it says *"Starting a session to handle this — one moment."*

1. **Triage:**
   ```text
   Flood warning for Lagos. 22 SMS messages just came in from the gateway. @intake triage the inbox now and post a short summary.
   ```
   ✅ In about 40 seconds intake makes **20 cases**, skips **2** (a BVN scam and a thank-you note), and
   **mentions @verify by itself**, listing the bridge claim and the likely duplicate families. The map fills with dots.

2. **Verify:** no message needed, because intake already handed over. ✅ verify starts its own session, merges the
   duplicate reports (for example *"Case #10 is a duplicate of #1 (now 3 reports)"*), and records
   **RUMOUR BLOCKED: Third Mainland Bridge collapsed**, citing the two eyewitnesses. The bridge dots turn purple.

3. **Dispatcher role and proposals:**
   ```text
   @dispatch first define an exclusive Switch role named dispatcher ("matches verified cases to rescue resources") and take it. Then propose resources for the 3 most critical verified cases and ask me to approve.
   ```
   ✅ Switch posts *"🎭 assumed the `dispatcher` role"*. dispatch proposes **D1 to D3** with reasons (for example,
   it notices a boat holds only 8 people for a group of 12) and asks you to approve.

4. **Human approval (the safety gate):** reply `@dispatch approve`. Always tag the agent: Switch only passes a
   message to an agent when it is @mentioned (or when you reply inside that agent's own thread).
   ✅ dispatch tries to run `dispatch send`, and **Switch stops it**. In the message's **thread** you see
   *"Permission needed · request A1 · Send dispatch D1…"*. Approve each request with its button, or reply in the
   thread with `A1 1`, `A2 1`, `A3 1`. ✅ Each one shows *"Chosen by @you from Mattermost"*, green route lines appear
   on the map, and `python relief.py dispatch list` shows `"status": "sent"` and `"approved_by"`.

5. **Exclusive role check:**
   ```text
   !roles
   ```
   ✅ *"dispatcher (exclusive) — 🟢 held by dispatch"*. Now ask standby to take over while dispatch still holds it:
   ```text
   @standby take over the exclusive dispatcher role now and continue where dispatch stopped.
   ```
   ✅ standby refuses, because the lease is still held: *"Can't take the dispatcher role yet… Switch refuses me."*
   Two agents can never hold the dispatcher role at the same time.

6. **Handover to standby:**
   ```text
   @dispatch you are going offline now (shift change). Release the dispatcher role immediately so @standby can take over, confirm in one line, and stop working.
   ```
   ✅ *"🎭 released the `dispatcher` role"*, then immediately *"🎭 assumed the `dispatcher` role"* by standby.
   dispatch posts a handover summary, and standby says *"STANDBY: dispatcher role taken. Picking up where dispatch
   left off"* and proposes the next rescues (D4 to D6). Approve with `@standby approve D4, D5, D6` and allow each
   request in the thread. `!roles` now shows standby holding `dispatcher`.

7. **Close a case:**
   ```text
   @standby field team confirms case 14 rescued, both men out of the water. Mark it rescued.
   ```
   ✅ The Ajah dot turns green and its boat is free again.

Run `python relief.py sitrep` at any point for the live numbers.

**Troubleshooting**
- **Agents don't answer in Town Square:** that channel isn't a Switch room. Use `flare-hq` (Step 5).
- **"Starting a session…" then nothing:** Switch Console must stay open, because agents only run while it runs.
  Check that Claude Code is signed in (`claude --version`).
- **The Mattermost switch is greyed out on Windows:** see the Docker note in Step 2.
- **A role won't move to standby:** the holder's session must release it or stop. Removing an agent from one room
  (`!remove-agent`) does not stop its session, so it keeps the lease.
- **The map is empty:** `serve` and the agents must use the same `flare` folder, because the board lives in `flare/data/relief.db`.
- **`unknown place`:** run `python relief.py geo "<name>"` to list the known places.

**What Part B does not cover yet:** the Telegram field room, the sitrep agent and zone rooms are written
(`agents/sitrep`, `switch/room-instructions.md`) but were not run in the recorded test. The standby takeover was
tested as a planned handover (dispatch releases the role). Switch also releases the role on its own a few
seconds after the holder's session stops, but we did not trigger that automatic path.

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
- The approval is enforced below the agent, not by its instructions: `agents/dispatch` and `agents/standby` list every
  form of `dispatch send` as an **ask** rule, and **deny** `cd`, `python -c`, direct database access and edits to their
  own rules. In testing, an agent that changed folders slipped past a narrower rule, so the rules were hardened and
  re-tested: Switch's *Permission needed* prompt now appears every time.
- Public field rooms never receive names, phone numbers or exact addresses.

## License

MIT
