# Multiplayer Implementation Plan — Tavern Tales Reborn

**Status:** Approved planning document. Not yet implemented.
**Date:** 2026-04-28

This plan adds two-player multiplayer to Tavern Tales. The host runs the FastAPI backend and Ollama; the guest connects via browser. Player prompts are private; AI narration is shared. Turns are sequential.

---

## 1. Confirmed Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Turn structure | **Sequential** — one player has the floor at a time. After both submit, AI generates. |
| 2 | Player characters | **Each player controls their own distinct character.** |
| 3 | Guest preference sharing | **Both options.** Guest can either fill in a lightweight in-lobby form OR paste an exported preference JSON from their own Tavern Tales instance. |
| 4 | Network scope | **LAN-first.** Infrastructure must be tunnel-compatible (ngrok / Cloudflare Tunnel) with no code changes for future internet support. |
| 5 | Disconnect handling | **Pause and wait for reconnect** (configurable window, default 5 minutes). After timeout, host can choose to eject and continue solo or archive the session. |
| 6 | Session persistence | **Resumable.** Sessions persist to disk. Host has explicit "Delete Session" control. |

## 2. Confirmed Suggestions (all approved)

1. **Room codes** (6-char alphanumeric like `WOLF42`) instead of raw IPs.
2. **Lobby / Session Zero** before play — both players review merged preferences and click Ready.
3. **Veto semantics** for preference conflicts — most restrictive setting wins.
4. **"Partner submitted" indicator** without revealing prompt text.
5. **OOC chat sidebar** for coordination outside the narrative.
6. **Joint action shortcut** — both players commit identical "we act together" text.
7. **Session narrative export** — AI responses only, prompts excluded.
8. **Spectator mode** designed-for but not implemented (read-only WS connection).

---

## 3. Architecture Overview

```
Host Machine:
  [Ollama] ← [FastAPI + WebSocket Server (port 8000)] ← [Host Browser]
                           ↑
                  [Guest Browser]
                  (LAN: http://192.168.x.x:8000)
                  (Internet: ngrok / Cloudflare Tunnel — documented only)
```

No new servers. No accounts. The host's existing FastAPI instance gains WebSocket support and a session manager. The guest opens a browser and connects directly. Tunnel solutions work transparently — WebSocket and REST endpoints don't need code changes for internet mode.

### Sequential Turn Flow (canonical)

```
Turn N starts (active_slot = host on turn 0, alternates after every AI response)

  Active player has the floor:
    - Their input box is unlocked, they type their action
    - Other player sees: "{ActiveName} is composing..."
    - Active player submits
      → Their action is stored privately on the server

  → AI generates from that single attributed action
  → Tokens stream to BOTH players in real time (identical broadcast)
  → AI completes, turn_id assigned, side effects applied to the acting player

Turn N+1 starts (active_slot flips to the other player)
```

The AI sees one attributed player action at a time, creating a "yes, and" cadence:
Player 1 prompt → AI response → Player 2 prompt → AI response.

---

## 4. Phase 1 — Session Infrastructure

### 4.1 New module: `backend/session_manager.py`

```python
class SessionStatus(str, Enum):
    LOBBY              = "lobby"
    HOST_TURN          = "host_turn"        # host has the floor
    GUEST_TURN         = "guest_turn"       # guest has the floor
    GENERATING         = "generating"       # AI producing output
    PAUSED             = "paused"           # a player disconnected
    ARCHIVED           = "archived"         # host ended the session

class PlayerSlot(str, Enum):
    HOST  = "host"
    GUEST = "guest"

class ConnectedPlayer(BaseModel):
    slot: PlayerSlot
    display_name: str
    character_name: str
    connection_id: str
    is_ready: bool = False
    is_connected: bool = True
    preference_profile: dict | None = None      # raw imported JSON OR built from lobby form
    preference_source: Literal["imported", "lobby_form", "none"] = "none"

class PendingAction(BaseModel):
    slot: PlayerSlot
    text: str
    submitted_at: datetime

class SessionState(BaseModel):
    room_code: str
    campaign_id: str
    status: SessionStatus
    players: dict[str, ConnectedPlayer]              # keyed by slot
    pending_actions: dict[str, PendingAction]        # keyed by slot
    turn_number: int = 0
    starting_slot_this_round: PlayerSlot = PlayerSlot.HOST  # active slot marker
    paused_since: datetime | None = None
    paused_status_before: SessionStatus | None = None       # state to restore on reconnect
    created_at: datetime
    last_activity: datetime
    reconnect_window_seconds: int = 300              # 5-minute default
```

**Core methods:**

| Method | Purpose |
|--------|---------|
| `create_session(campaign_id) → str` | Generates room code, persists session metadata |
| `join_session(room_code, ws, player_info) → PlayerSlot` | Returns assigned slot; rejects if both filled |
| `set_ready(room_code, slot, is_ready)` | Updates ready state; transitions to HOST_TURN if both Ready |
| `submit_action(room_code, slot, text)` | Stores pending action; transitions floor / triggers generation |
| `current_active_slot(session) → PlayerSlot` | Derives whose turn it is based on `status` |
| `broadcast(room_code, message)` | Sends JSON to all connected WS clients in session |
| `broadcast_to(room_code, slot, message)` | Sends JSON to a single slot |
| `mark_disconnected(room_code, slot)` | Saves prior status, transitions to PAUSED |
| `mark_reconnected(room_code, slot)` | Restores prior status if within reconnect window |
| `eject_guest(room_code)` | Host action — removes guest, transitions campaign to single-player |
| `archive_session(room_code)` | Host action — marks ARCHIVED, preserved on disk |
| `delete_session(room_code)` | Host action — destructive removal of session and campaign |
| `cleanup_expired_paused_sessions()` | Background task — auto-archive sessions paused > 24h |

Sessions persist to `backend/sessions/{room_code}.json`. WebSocket connection refs are kept in-memory only (a separate `connections: dict[room_code → dict[slot → WebSocket]]` registry, not serialized).

### 4.2 WebSocket endpoint (added to `backend/main.py`)

```
WS /api/session/{room_code}/ws
```

**Client → Server messages:**

| `type` | Fields | Description |
|--------|--------|-------------|
| `join` | `display_name`, `character_name`, `preference_profile?`, `preference_source` | First message after connecting |
| `ready` | — | Confirms lobby review complete |
| `unready` | — | Pulls back ready state |
| `submit_action` | `text` | Submit narrative input (only valid when slot has the floor) |
| `ooc_message` | `text` | Out-of-character chat (not sent to AI) |
| `eject_guest` | — | Host-only: remove guest, revert to single-player |
| `archive_session` | — | Host-only: end session but keep on disk |
| `delete_session` | — | Host-only: destructive removal |
| `reconnect` | `slot`, `connection_id` | Player rejoining within reconnect window |

**Server → Client messages:**

| `type` | Audience | Fields | Description |
|--------|----------|--------|-------------|
| `session_state` | All | full `SessionState` + `merged_preferences` | Full sync on join/reconnect |
| `player_joined` | All | `slot`, `display_name`, `character_name` | New player connected |
| `player_ready` | All | `slot`, `is_ready` | Ready toggled |
| `floor_passed` | All | `active_slot` | Whose turn it is now |
| `partner_composing` | Inactive slot only | `active_slot` | Partner is typing (no content) |
| `generation_start` | All | `turn_number` | AI beginning to generate |
| `token` | All | `text` | Streaming token (identical broadcast) |
| `generation_done` | All | `turn_number`, `turn_id`, `next_active_slot` | AI turn complete; floor passes |
| `ooc_message` | All | `slot`, `display_name`, `text` | OOC chat |
| `session_paused` | All | `disconnected_slot`, `reconnect_deadline` | Player dropped |
| `session_resumed` | All | `slot` | Player reconnected within window |
| `session_archived` | All | `reason` | Host archived |
| `player_ejected` | All | `slot` | Host removed guest |
| `error` | Sender | `message`, `code` | Validation or state error |

### 4.3 New REST endpoints (added to `backend/main.py`)

```
POST /api/session/create
  Body:    {campaign_id}
  Returns: {room_code, join_url, lan_ip, session_state}

GET  /api/session/{code}/state
  Returns: current SessionState (for HTTP-side reconnect check before WS upgrade)

POST /api/session/{code}/leave
  Graceful disconnect

POST /api/session/{code}/archive
  Host-only. Marks session ARCHIVED but preserves on disk.

DELETE /api/session/{code}
  Host-only. Destructive removal.

POST /api/session/{code}/export
  Returns: narrative-only document (AI responses + system events; prompts excluded)

GET  /api/server/info
  Returns: {lan_ip, port, version} — used by lobby UI for join URL display
```

---

## 5. Phase 2 — Campaign Schema Extension

### 5.1 Changes to `backend/schema.py`

```python
class PlayerCharacter(BaseModel):
    slot: Literal["host", "guest"]
    name: str
    gender: str = ""
    appearance: str = ""
    description: str = ""
    location: str = ""
    stats: dict[str, int] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)

class MultiplayerConfig(BaseModel):
    room_code: str
    host_character: PlayerCharacter
    guest_character: PlayerCharacter | None = None
    merged_preference_context: CampaignPreferenceContext | None = None
    session_status: SessionStatus = SessionStatus.LOBBY
    starting_slot_this_round: PlayerSlot = PlayerSlot.HOST
```

Add to `CampaignState`:

```python
multiplayer: MultiplayerConfig | None = None
# existing `player` field stays — used for single-player campaigns and unaffected
```

Extend `Message`:

```python
player_slot: Literal["host", "guest"] | None = None
# attribution for user messages; None means combined or single-player
```

### 5.2 Changes to `backend/state_manager.py`

- `apply_state_delta(state, delta, player_slot=None)` — when `player_slot` is provided, route stat / inventory / location changes to the matching `PlayerCharacter` instead of `state.player`
- `apply_reversal(state, reversal, player_slot=None)` — symmetric handling
- New helpers: `get_multiplayer_config`, `update_multiplayer_config`, `set_guest_character`

### 5.3 Migration

Schema v2 does not auto-migrate. Existing single-player campaigns continue to work unchanged (`multiplayer=None`). New multiplayer sessions create new campaigns with `multiplayer` populated. No backfill required.

---

## 6. Phase 3 — Turn Engine

### 6.1 Sequential turn state machine (in `session_manager.py`)

```
LOBBY
  └─ both players Ready? → HOST_TURN [turn 0]

HOST_TURN
  ├─ host submit_action → store, transition → GENERATING
  └─ guest submit_action → REJECTED (not your turn)

GUEST_TURN
  ├─ guest submit_action → store, transition → GENERATING
  └─ host submit_action → REJECTED (not your turn)

GENERATING
  └─ AI complete → clear pending_actions
                 → flip active slot
                 → status = (other slot)_TURN

[during HOST_TURN | GUEST_TURN | GENERATING]
  └─ player disconnect → save status, transition → PAUSED

PAUSED
  ├─ within reconnect window: player reconnects → restore status
  ├─ within window: host eject_guest → restore status as single-player
  ├─ window expires: host eject_guest → archive session
  ├─ host archive_session → ARCHIVED
  └─ host delete_session → fully removed

ARCHIVED
  └─ host delete_session → fully removed
```

`starting_slot_this_round` is now the active slot marker and flips after every AI response. Turn 0: host. Turn 1: guest. Turn 2: host. And so on.

### 6.2 New function in `backend/main.py`: `_run_multiplayer_turn(room_code)`

1. Acquire `state_manager.turn_lock(campaign_id)` — same exclusive write lock as single-player.
2. Load current `CampaignState`.
3. Append one attributed user `Message` for the acting slot.
4. Call `prompt_builder.build_prompt()` with the multiplayer flag — emits the new PARTY block and merged preference context.
5. Stream tokens from Ollama. For each token, call `session_manager.broadcast(room_code, {type: "token", text: token})` — both clients receive the same token in the same order.
6. On stream complete:
   - Append assistant `Message` with the streamed content
   - Run multiplayer postprocessing for the acting slot. Reversal is stored with that slot in `MessageSideEffects`.
7. Reset `pending_actions = {}`.
8. Flip the active slot. Transition `status` to that slot's `_TURN`.
9. Broadcast `generation_done` with `next_active_slot`.

### 6.3 Race conditions and safety

- `submit_action` validates `slot == current_active_slot(session)`. Mismatched submissions return `error` with code `not_your_turn`.
- During `GENERATING`, all submissions return `error` with code `generation_in_progress`.
- `asyncio.Lock` per session protects state transitions inside `session_manager`.
- The existing `state_manager.turn_lock(campaign_id)` continues to gate disk writes.

### 6.4 Disconnect / Reconnect handling

- On WS close: `mark_disconnected(slot)` — saves `paused_status_before = status`, sets `status = PAUSED`, sets `paused_since = now`.
- Broadcast `session_paused` with `disconnected_slot` and `reconnect_deadline = paused_since + reconnect_window_seconds`.
- Other player's input is locked. UI shows "Partner disconnected — waiting up to {N}m".
- On reconnect (matching `connection_id`): `mark_reconnected(slot)` — restores `status = paused_status_before`. Broadcast `session_resumed` and full `session_state`.
- On window expiry: server emits `session_paused` again with a `host_action_required` flag. Host UI shows "Eject and continue solo" / "Archive session" buttons.

---

## 7. Phase 4 — Prompt Engineering

### 7.1 Changes to `backend/prompt_builder.py`

When `state.multiplayer` is populated, replace the single `PROTAGONIST` block with a `PARTY` block:

```
## PARTY

You are narrating for TWO players, each controlling their own character.
Address both characters in your narration. Weave their actions together
into a single cohesive narrative beat. Each player only sees your output —
they do not see each other's typed actions, so make sure your narration
makes both characters' contributions visible.

### {HOST_CHARACTER_NAME} (Player 1)
Location: {location} | Gender: {gender}
Appearance: {appearance}
{description}
Stats: {stats} | Inventory: {inventory}

### {GUEST_CHARACTER_NAME} (Player 2)
Location: {location} | Gender: {gender}
Appearance: {appearance}
{description}
Stats: {stats} | Inventory: {inventory}
```

### 7.2 Attributed user message format

Each multiplayer AI turn produces a single user `Message` for the acting player:

```
[{ACTING_CHARACTER_NAME}]: {action_text}
```

The next player responds to the AI's latest narration, preserving a turn-by-turn "yes, and" flow.

### 7.3 Token budgeting

Each character block is estimated and tracked in `BlockTokens` the same way the existing `PROTAGONIST` block is. The `system_reserve` budget in `prompt_builder` may need a small bump (~200 tokens) to accommodate two character cards.

### 7.4 Privacy model

The privacy boundary is enforced at the WebSocket broadcast layer, not the prompt layer:

- `submit_action` text is **never** included in any `partner_composing` broadcast.
- The attributed user message exists in the `messages` list inside `CampaignState`, so anyone with director-mode or `/api/state/{id}` access can see it. This is intentional — the host is the campaign owner. Guests have **no** access to raw state, only WS broadcasts.
- The `/api/state/{id}` endpoint should reject GET requests from non-host slots in multiplayer sessions (new authorization check).

---

## 8. Phase 5 — Preference Merging

### 8.1 New module: `backend/preference_merger.py`

```python
def merge_preferences(
    host_profile: UserPreferenceProfile | None,
    guest_profile: UserPreferenceProfile | None,
    context: ContextType = ContextType.MULTIPLAYER,
) -> CampaignPreferenceContext:
```

**Merge algorithm per preference item:**

1. **Filter by context** — only items where `ContextType.MULTIPLAYER` is in `item.context` are considered. Items only marked for `ai` or `partner` context are excluded.
2. **Hard veto** — if either player has `realWorldWillingness = hard_no` OR `textRoleplayWillingness = no` → item is **excluded** from the merged whitelist entirely.
3. **Soft veto** — if either player has `realWorldWillingness = soft_no` OR `textRoleplayWillingness = maybe` → item is included but flagged as "approach with care" in the guidance text.
4. **Intensity** — `min(host_intensity, guest_intensity)`. More conservative wins.
5. **Fantasy interest** — `min(host_interest, guest_interest)`.
6. **Overlap-only items** — if either player has `partnerSharePermission = overlap_only`, item is only included if **both** players have interest ≥ `low`.
7. **Fade-to-black** — if either player has `fadeToBlack = true` globally, the merged context is fade-to-black.
8. **Output** — `CampaignPreferenceContext` with merged `theme_whitelist` and a generated `preference_guidance_text` block noting any soft vetoes.

### 8.2 Null handling

- One profile is None → other profile is used as-is (after filtering by `MULTIPLAYER` context).
- Both profiles are None → empty `CampaignPreferenceContext` (no guidance block in prompt).

### 8.3 Lobby presentation

The merged context is stored in `MultiplayerConfig.merged_preference_context`. Both players see it in the lobby as a **read-only summary**:

- "Themes you'll see in this session: {comma-separated whitelist}"
- "Things you've both excluded: {soft and hard vetoes}"
- "Intensity ceiling: {min intensity}"
- "Fade-to-black: {yes/no}"

Either player can click "Unready" if they're not comfortable, which blocks the campaign from starting. This is the explicit consent gate.

---

## 9. Phase 6 — Frontend

### 9.1 New component: `MultiplayerLobby.jsx`

**Host view:**
- Room code displayed prominently (e.g., `WOLF42`)
- LAN URL display: `Connect at: http://192.168.x.x:8000`
- Copy-to-clipboard button for the join URL
- Host character card (name, gender, appearance, description — editable pre-game)
- Guest character card placeholder (locked until guest joins)
- Merged preference accordion (view-only, collapsible)
- Ready button (enabled once guest joined and host character set)
- "Revert to single-player" link
- "Delete session" button (destructive, confirmation modal)

**Guest view:**
- Room code entry field
- Character setup form (name, gender, appearance, description)
- **Preference setup with two paths:**
  - Tab 1: "Quick setup" — lightweight in-lobby form (7 categories, simplified yes/no/maybe responses)
  - Tab 2: "Import from Tavern Tales" — paste exported preference JSON
  - Tab 3: "Skip" — proceed with no guest preferences (host preferences used as-is)
- Host character card (view-only once connected)
- Merged preference accordion (live-updating as guest fills form)
- Ready button

### 9.2 New / extended component: `MultiplayerPlay.jsx`

Renders the in-game view. Either replaces or wraps the existing `App.jsx` chat view depending on whether a campaign has `multiplayer` populated.

**Chat log changes:**
- Your own submitted action: subtle grey pill `(You) [action submitted — hidden from partner]`
- Partner's submitted action: subtle grey pill `(Partner) [action submitted]`
- AI narrative response: rendered normally, identical to single-player display
- OOC messages: distinct visual treatment (italic, muted color, `[OOC] {display_name}: text`)

**Input area state machine:**

| State | Input | Helper text |
|-------|-------|-------------|
| `HOST_TURN` and you are host | Enabled | "Your turn — type your action" |
| `HOST_TURN` and you are guest | Locked | "{HostCharName} is composing..." |
| `GUEST_TURN` and you are guest | Enabled | "Your turn — type your action" |
| `GUEST_TURN` and you are host | Locked | "{GuestCharName} is composing..." |
| `GENERATING` | Locked | "AI is writing..." |
| `PAUSED` | Locked | "Partner disconnected — waiting up to {N}m" |

**Turn indicator** (top of chat):
- `Turn 1 — {Name}'s turn`
- `Turn 1 — AI is writing...`
- `Turn 2 — {Name}'s turn`

**Player roster panel** (collapsible sidebar):
- Both players: avatar, character name, display name, connection dot (green/red), Ready checkmark
- Host badge on host slot
- (Host-only) Eject / Archive / Delete buttons

**OOC chat sidebar** (collapsible):
- Simple text input + recent message log (in-memory only — NOT persisted, NOT sent to AI)
- Visual separation from main narrative chat

**Joint action button:**
- Visible only when it's your turn
- Single click pre-fills the input with `(joint action with {PartnerName})` and submits — both players' inputs collapse into "We act together: {action}" when AI generates

### 9.3 New hook: `frontend/src/hooks/useMultiplayerSession.js`

Wraps the WebSocket lifecycle:

- Connect on mount with exponential backoff reconnect (max 5 attempts → "Connection lost" banner)
- Dispatch incoming server messages to a `sessionState` reducer
- Expose: `sessionState`, `isConnected`, `mySlot`, `submitAction(text)`, `sendOOC(text)`, `readyUp()`, `unready()`, `ejectGuest()`, `archiveSession()`, `deleteSession()`
- On reconnect: send `{type: "reconnect", slot, connection_id}` to re-register

### 9.4 Changes to `CampaignCreator.jsx`

- Add a "Multiplayer" toggle on the campaign creation form
- When enabled: host fills in their own character during creation; guest character section is grayed out with "Guest will fill in during lobby"
- On campaign create: if multiplayer, auto-call `POST /api/session/create` and redirect to lobby
- Document the implication clearly: "Multiplayer sessions are persisted and resumable. The session can only be joined while the host's server is running."

### 9.5 Authorization

- Guest browsers should never call `/api/state/{id}` directly. Add a simple slot check on these endpoints: in multiplayer mode, GET/PATCH/PUT require a header indicating the host slot. This prevents a guest from snooping on the full message history (where their partner's prompts would be visible).

---

## 10. Phase 7 — Network

### 10.1 LAN mode (built-in)

Change FastAPI startup to bind all interfaces:

```bash
# In start_all.bat and uvicorn launch:
uvicorn main:app --host 0.0.0.0 --port 8000
```

New endpoint surfaces the host's LAN IP:

```
GET /api/server/info  →  {lan_ip: "192.168.1.47", port: 8000, version: "..."}
```

The lobby UI calls this on session creation and displays the join URL prominently.

**LAN IP detection** — in `main.py`, use a small helper that opens a UDP socket to `8.8.8.8:80` (no traffic actually sent) and reads the local socket address. Standard cross-platform Python idiom for finding the active LAN IP. Falls back to `127.0.0.1` if no LAN.

### 10.2 Internet mode (documented, not implemented)

New file: `MULTIPLAYER_NETWORK.md` in the repo root. Documents two options:

1. **ngrok** (free tier, temporary URL):
   ```
   ngrok http 8000
   ```
   Share the `https://xxxx.ngrok.io` URL with the guest.

2. **Cloudflare Tunnel** (free, persistent subdomain):
   ```
   cloudflared tunnel run
   ```

The guest uses the tunnel URL instead of the LAN IP. **No code changes required** — the WebSocket and REST endpoints work through these tunnels because they're standard HTTP/WS.

### 10.3 Security notes (documented)

- **Room codes are the only authentication.** Anyone with the code who can reach the host's server can join as the guest.
- For LAN: acceptable. Trusted home network.
- For internet/tunneling: codes should be treated as short-lived passwords. Document that users should regenerate codes between sessions.
- Future hardening: optional shared-secret PIN for high-trust internet sessions. **Out of scope for v1.**

---

## 11. Phase 8 — Tests

### 11.1 Backend test files

**`backend/tests/test_session_manager.py`**
- Create session, generate unique room codes (test collision avoidance)
- Join first player → slot = "host"; join second → slot = "guest"; join third → rejected
- `submit_action` from non-active slot → rejected with `not_your_turn`
- Submit active action → status transitions to `GENERATING`
- After generation → active slot flips and status transitions to the other player's `_TURN`
- Disconnect during `GUEST_TURN` → status = `PAUSED`, `paused_status_before = GUEST_TURN`
- Reconnect within window → status restored
- Reconnect after window expires → host receives `host_action_required`

**`backend/tests/test_multiplayer_prompt.py`**
- Multiplayer campaign state → `PARTY` block present in system prompt
- Both character sections (host + guest) appear with correct names, stats, inventory
- Attributed user message format `[Name]: text` for the acting player
- Merged preference block appears
- Single-player campaign → `PARTY` block absent (regression check on `test_second_turn_prompt_contains_world`)

**`backend/tests/test_preference_merger.py`**
- Hard veto: one player `hard_no` → item excluded from merged whitelist
- Soft veto: one player `soft_no` → item included but flagged in guidance text
- Intensity minimum: host=`intense`, guest=`light` → merged=`light`
- Overlap-only: item only in merged if both players have interest ≥ `low`
- Fade-to-black: either player true → merged true
- Null host profile → guest profile used (filtered by MULTIPLAYER context)
- Null both profiles → empty `CampaignPreferenceContext`
- Context filter: items marked `ai` only do not appear in merged output

**`backend/tests/test_multiplayer_chat_flow.py`**
- End-to-end: create session → both join → both ready → host submits → mock Ollama stream → verify token broadcasts → verify attributed user message stored → verify state delta applied to host → guest submits next turn → verify floor alternates

### 11.2 Manual QA checklist

Two browser windows, one at `localhost:5173` (host) and one at `{host_ip}:5173` (guest, ideally a second device on same LAN).

- **Happy path**: create session → guest joins → both fill in characters → both ready → host turn → submit → AI streams to both → guest turn → submit → AI streams to both → host turn resumes
- **Privacy check**: confirm guest never sees host's submitted text in any UI surface, network response, or WS message
- **OOC chat**: messages appear in both clients; do not appear in narrative; not persisted after session ends
- **Joint action**: both players use joint action button → AI receives "We act together"
- **Disconnect during `GENERATING`**: kill guest WS mid-stream → host sees PAUSED banner → reconnect guest → session resumes from where it was
- **Disconnect timeout**: kill guest, wait > 5 minutes → host gets eject/archive prompt
- **Eject and continue**: host ejects guest mid-session → campaign reverts to single-player gracefully
- **Resume session**: archive session → restart server → load campaign → confirm session state restored, players need to rejoin
- **Delete session**: host clicks delete → campaign and session both removed → no orphaned files
- **Preference veto**: guest fills lobby form with `hard_no` on item host favors → merged whitelist excludes it → confirm AI guidance reflects exclusion
- **Tunnel test (manual, optional)**: run ngrok → guest connects via tunnel URL → confirm same UX as LAN

---

## 12. Implementation Order and Effort

| Phase | What | Size | Depends on |
|-------|------|------|------------|
| 2 | Schema extension (PlayerCharacter, MultiplayerConfig, Message attribution) | S | — |
| 5 | Preference merger | S | — |
| 1 | Session manager + WebSocket endpoint | M | 2 |
| 3 | Turn engine + multiplayer chat handler | M | 1, 2 |
| 4 | Prompt engineering (PARTY block, combined message) | S | 2 |
| 7 | Network (bind 0.0.0.0, server info endpoint, docs) | XS | 1 |
| 6 | Frontend (lobby, play screen, WS hook) | L | 1, 3, 4, 5 |
| 8 | Tests | M | 1–6 |

S = Small, M = Medium, L = Large, XS = Extra Small

**Recommended build order: 2 → 5 → 1 → 3 → 4 → 7 → 6 → 8**

Schema and preference merger are pure data layers with no integration risk. Session manager and turn engine form the critical path. Prompt engineering rides on the schema. Network and tests come once the backend is stable. Frontend last because it depends on every other layer being functional and testable via a CLI / curl first.

**Total estimate: 4–5 days of focused implementation.**

---

## 13. Out of Scope (v1)

The following are deliberately deferred to keep v1 scope tight:

- **3+ players.** Architecture allows extension (`PlayerSlot` enum becomes open), but UI and prompt design are 2-player. Adding more players is mostly schema + UI work.
- **Spectator mode.** Read-only WebSocket connections. The session manager is designed to allow these (additional `spectators: list[ConnectedPlayer]`) but the UI and access controls are not built.
- **Internet-mode auth hardening.** Optional shared-secret PIN, IP allowlists, etc.
- **Cross-host campaign migration.** Importing a multiplayer session from another host's machine.
- **Session replay UI.** Dedicated viewer for archived sessions — for now, archived sessions are loadable as read-only campaigns.
- **Voice chat / video.** Out of scope; users coordinate via Discord or similar.

---

## 14. Open Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Token budget overflow with two character blocks + merged preferences | Bump `system_reserve` by ~200 tokens; log warning and truncate `RECENT EVENTS` first |
| Guest browser snoops on `/api/state/{id}` to read partner's prompts | Add slot-aware authorization on read/write state endpoints |
| Race between WS disconnect and incoming `submit_action` | Use per-session asyncio.Lock around all state transitions |
| Long AI generations exceed reconnect window | If a player disconnects during `GENERATING`, save the partial response and resume on reconnect — don't abandon the turn |
| Schema v2 → v3 breaking change | Feature-gate `multiplayer` field as nullable; existing campaigns are unaffected; no migration needed |
| Guest preference JSON contains malicious / oversized content | Validate via `UserPreferenceProfile.parse_obj`; cap raw JSON at 100 KB |
| Host runs out of memory hosting many concurrent sessions | Cap concurrent active sessions at 5 per host (configurable); reject new sessions with friendly error |

---

## 15. Documentation Deliverables

- This file: `MULTIPLAYER_IMPLEMENTATION_PLAN.md`
- New: `MULTIPLAYER_NETWORK.md` (LAN setup + tunnel guides)
- Update: `CLAUDE.md` — add multiplayer section to module map
- Update: `README.md` — feature mention + how to start a multiplayer session
- Update: `IMPLEMENTATION_PLAN.md` — append multiplayer phase log

---

*End of plan.*
