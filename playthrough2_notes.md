# Tavern Tales Reborn — QA & UX Evaluation
**Evaluator Role:** QA Tester / UX Specialist  
**Date:** 2026-04-30  
**Scope:** Full application audit with extended focus on the multiplayer experience  
**Method:** Complete codebase review, user-flow tracing, feature inventory, and UX analysis

---

## Executive Summary

Tavern Tales Reborn is a remarkably capable local-LLM text RPG with a solid technical backbone. The single-player experience is polished and immersive. The multiplayer system is architecturally well-designed — session management, WebSocket lifecycle, preference merging, and reconnection logic are all implemented with care — but the *front-end multiplayer experience* lags significantly behind the single-player experience in functionality, feedback, and usability. The gap between what the backend *can do* and what the player *can see and control* in multiplayer mode is the single biggest opportunity for improvement.

---

## Section 1: Functionality

### 1.1 Single-Player — What Works Well

- **Streaming narration** is smooth; the "storyteller is weaving the thread…" pulse feedback is appropriate.
- **Kickoff scene** fires automatically when a campaign is loaded for the first time, establishing immersion immediately.
- **Director Mode** is a fully functional mid-game editor: stats, inventory, location, appearance, lorebook, and NPCs are all editable with undo and 409-conflict protection.
- **Reroll / Continue** buttons appear contextually after each GM response, which is excellent for iterative storytelling.
- **Turn-level rollback** (delete message) is properly guarded by a confirmation modal and reverses attributed state changes — a feature most competitors lack entirely.
- **Timeline Fork** duplicates a campaign at its current state, enabling players to explore alternate outcomes. The feature works correctly and the confirmation feedback via banner is appropriate.
- **Campaign import/export** covers the full state + memory bundle, making it genuinely portable.
- **Token context bar** gives power users real visibility into prompt consumption.
- **Memory system** (ChromaDB vector search) retrieves relevant past events and the Inspector lets users see exactly what was injected.

### 1.2 Single-Player — Functional Issues

**F-SP-01: No "pass turn" mechanism**  
There is no way to end a turn without submitting text. A player who wants to observe without acting must type something like "I wait." The AI should be instructable to let a turn pass (perhaps via a dedicated "Pass / Observe" button).

**F-SP-02: Quick Actions are template-only, not adaptive**  
The six Quick Actions (Attack, Persuade, Search, Sneak, Rest, Roll) insert hardcoded placeholder text like `"I attack [target] with [weapon]."`. The player must edit the brackets manually before sending. These should ideally be smart forms or at minimum expand on click with a small modal to fill in the blanks.

**F-SP-03: "Continue" condition is fragile**  
The `canContinue` condition checks if the last message does not end in `.!?…"'"`. A GM response ending in ellipsis or mid-sentence dialogue would incorrectly suppress the Continue button, while one ending in a quoted closing punctuation mark would suppress it even if the narrator cut off early.

**F-SP-04: Reroll silently drops partial messages**  
If a streaming response is stopped mid-way and the user hits Reroll, the partial content gets cleared but no confirmation is shown. Users may be confused about why their narrative disappeared.

**F-SP-05: Duplicate stat names allowed**  
The stats editor in CampaignCreator and Director Mode allows creating two stats with the same name. The second silently overwrites the first in the backend dict. Adding a uniqueness check would prevent data loss.

**F-SP-06: Lorebook keywords are organizational labels only — documented but easy to misunderstand**  
The UI says "keywords are for your own organization" but new users may expect keyword-triggered injection (like many lorebook implementations in the genre). A clearer in-UI description of what keywords actually do would prevent confusion.

**F-SP-07: No Ollama health-check feedback**  
If Ollama is not running when the player clicks "Begin Adventure," they see a generic 500 or connection error from the API. There is no proactive detection or friendly "Ollama is not running — please start it" message at the model-selection stage. The CampaignCreator does show a warning if no models are found, but only after the model list fetch fails silently on load.

**F-SP-08: World generation only generates one starting scene**  
The "Auto-Forge World" feature is powerful but produces a single linear result. There is no "regenerate" or "show 3 alternatives" option. If the AI produces a weak world, the user must manually clear all fields and re-prompt.

---

### 1.3 Multiplayer — What Works Well

- **WebSocket lifecycle** is robust: connects, disconnects, and reconnects are handled with a 5-attempt exponential backoff, and the backend holds a 5-minute reconnect window.
- **Session persistence across server restarts**: sessions rebuild from saved campaign state in PAUSED status — impressive resilience.
- **Preference merging with hard/soft veto**: the most-restrictive-player-wins semantics are correctly applied and visible in the lobby summary panel.
- **OOC chat** is cleanly separated from the narrative and carries the explicit disclaimer that the AI never sees it.
- **Partner composing indicator**: the typing debounce (350ms) and "partner is composing…" notification is a thoughtful addition.
- **Turn attribution in narration**: each NarrationBlock shows a colored left border and a badge labeling which player's action prompted the response — makes the narrative legible.
- **Client ID fingerprinting** for reconnect: the browser's session storage is used to regenerate the client's identity across refreshes without requiring the player to re-enter their slot.

### 1.4 Multiplayer — Functional Issues (Critical)

**F-MP-01: No opening scene / kickoff in multiplayer**  
Single-player campaigns always start with an AI-generated kickoff scene that sets the stage before the first player action. Multiplayer has no equivalent. The play screen says "No narration yet — the GM is waiting on the first turn." Players land in the game cold with no atmospheric context, no shared opening, nothing. The host's first action becomes the de facto kickoff. This should be a deliberate AI-narrated opening that both players receive before the first turn begins.

**F-MP-02: Guest character stats and inventory are invisible during play**  
The single-player sidebar shows the player's stats, inventory, location, and NPC cast at all times. The multiplayer play screen has only a Roster panel (name + connection dot) and OOC chat. Both players are completely blind to their own and their partner's character sheets during the session. If the AI says "your Health drops to 40," neither player has a panel showing the current value.

**F-MP-03: No player actions visible in the narrative**  
The session export endpoint (which populates the multiplayer narrative view) returns only GM/assistant turns. The user messages — what each player actually typed — are not shown. Players see a sequence of GM narration blocks tagged with "Prompted by [name]" but cannot read what their partner actually wrote. This is a critical gap for collaborative storytelling; partners need to see each other's declared actions.

**F-MP-04: WebSocket auto-reconnect gives up after ~15 seconds**  
The `RECONNECT_DELAYS_MS` array has 5 entries (500ms → 8000ms). After 5 failed attempts the hook dispatches a permanent error and stops. But the server holds the session for 5 minutes. If a player's network is intermittently flaky — common on Wi-Fi — the client gives up far before the server does, forcing a full page reload and re-entry of the room code.

**F-MP-05: No reconnect countdown shown to either player**  
When a partner disconnects, both players see "waiting up to 5 minutes for reconnect." There is no countdown timer showing how much time remains before the session auto-pauses or expires. The disconnected player's browser has already stopped reconnecting (per F-MP-04), leaving them confused about the state of the session.

**F-MP-06: OOC messages are ephemeral and cap at 50**  
Out-of-character messages exist only in the WebSocket hook's React state. They are lost on any page refresh and are hard-capped at the last 50. For a session spanning multiple hours with many coordination messages, this is inadequate. The backend has no persistence layer for OOC messages at all.

**F-MP-07: Turn order is fixed host-first with no override**  
The host always acts first, then it strictly alternates. There is no ability to change whose turn it is (e.g., guest goes first this scene), to allow a player to go twice in a row, or to pass a turn. The backend's `begin_next_round` simply flips the slot.

**F-MP-08: No Reroll or Continue in multiplayer**  
Single-player has ↻ Reroll and → Continue buttons after each GM response. These are absent in multiplayer. If the AI generates a poor or cut-off response, neither player can request a regeneration or extension. The session just advances to the next turn.

**F-MP-09: Guest has no session history if they join late or refresh**  
When a guest reconnects or a player refreshes, the play screen calls the session export endpoint to load the narrative. But the export only includes non-kickoff assistant turns from that session. If the session ran for many turns before the guest joined, they get the full narrative history — but if that export call fails (network hiccup), they land on an empty screen with no retry button, only a red error banner.

**F-MP-10: No way to return a multiplayer campaign to single-player mode**  
Once a session is created, the campaign is locked into multiplayer. If the guest stops playing and the host wants to continue solo, they must archive the session and start an entirely new campaign. There is no "eject guest and continue as single player" flow that transitions the host back to the single-player play screen.

**F-MP-11: Guest cannot find their previous session from the menu**  
The main menu shows "Or Continue Journey" with the player's saved campaigns. Guests never create campaigns, so this list is empty for them. There is no "Sessions I've Participated In" or "Rejoin by Room Code" option on the menu. A guest who closes their browser must ask the host for the room code again and re-enter through "Join Multiplayer Session."

**F-MP-12: Host must pre-create a campaign before hosting multiplayer**  
To host a new multiplayer game, the host goes through the full single-player "Forge Your World" setup screen alone, selects models, fills in protagonist details, then at the very bottom checks "Host this as a multiplayer session." The guest plays no part in world creation. There is no collaborative world-building step where both players contribute to the starting setup.

**F-MP-13: Single character edit slot per player in lobby**  
The guest can only edit one character card — their own. If the guest wants to suggest a different starting location or appearance for the host's character, there is no mechanism for that. Lobby cards are strictly self-editable.

**F-MP-14: Archived sessions cannot be converted back to single-player campaigns**  
When a session is archived, the campaign's multiplayer config is marked `ARCHIVED` but the campaign data is preserved. However, loading that campaign from the main menu shows the "Host" button as the only multiplayer option (it detects the active session). There is no "strip multiplayer config and play solo" path.

---

## Section 2: UX Design

### 2.1 Overall Aesthetic
The dark fantasy aesthetic is excellent — amber accents on a near-black background, serif fonts for narrative and sans-serif for UI chrome. This is one of the app's strongest qualities and should be preserved as the UI grows.

### 2.2 Single-Player UX Issues

**UX-SP-01: "Commit" is a developer label**  
The send button says "Commit" (a git term). Most players will understand "Send," "Act," "Declare," or even just "↵" better. The label causes momentary friction on first encounter.

**UX-SP-02: No first-run onboarding**  
The HelpModal exists and is well-written, but it is never surfaced automatically. A first-time user sees a large campaign creation form with no guidance. A first-run tooltip sequence or even a "New? Click here first" banner would dramatically reduce abandonment.

**UX-SP-03: Campaign list shows raw IDs**  
Each campaign in the menu shows its machine-generated ID (`campaign_1746000000000`) in small gray text next to the title. This is internal plumbing visible to users. It could be hidden entirely or replaced with "created [date]."

**UX-SP-04: "Forge Your World" screen is overwhelming**  
The setup screen has 5 major sections, each with multiple fields, before the player can start. The recommended flow — Auto-Forge World, then review and adjust — is not communicated. New users may attempt to manually fill every field and give up. A "Quick Start" mode that collapses to just a world prompt and a character name, with all other fields having sensible defaults, would make the onboarding far less daunting.

**UX-SP-05: Story Summary field in world setup has no purpose hint**  
The "World Description & Lore" and "Starting Scene" fields are auto-populated by the AI, but there is also a silent `storySummary` field that is initialized from drafts. It is sent to the backend but has no corresponding visible label in the UI after the AI fills it. Users who look in the network inspector might be confused about what is actually being sent.

**UX-SP-06: Director Mode discovery is low**  
"Director Mode" is a button in the header but nothing communicates that it exists to first-time players. First-time users who want to edit a stat mid-game have no idea this feature is available. The button label alone gives no hint of what it does. A subtle "(edit world state)" label or header tooltip would help.

**UX-SP-07: Action roll result shown as a small badge, easy to miss**  
When a risky action triggers a d20 roll, the result appears as a small green badge in the header toolbar. For players unfamiliar with the feature, this is easy to miss entirely. The roll outcome should appear inline in the narrative view, more prominently and perhaps before the GM response starts streaming.

**UX-SP-08: Token usage bar is unlabeled for non-technical users**  
The context bar shows `12,432 / 32,768` with a color gradient but no label explaining what it means. A tooltip or "(AI memory capacity: 38% full)" label would make this meaningful to non-technical players.

**UX-SP-09: Quick Actions hidden by default and toggle state is subtle**  
The Quick Actions toggle (⚡ Actions ▸/▾) is a very small button above the input box. Many users will never find it. Consider making it visible by default for new users, then allowing them to hide it.

**UX-SP-10: No visual confirmation that a preference profile is actively influencing the session**  
The sidebar shows a green "Preference Context" block, but only if `preference_context.enabled` is true. The connection between the profile system and the actual in-game behavior is invisible. A small "Preferences active" indicator or turn-by-turn confirmation ("GM is respecting your boundaries") would increase trust in the system.

**UX-SP-11: "Fork Timeline" is developer-speak**  
"Fork" is a git term. "Duplicate Campaign at this Moment," "Explore Alternate Path," or "Create Branching Story" would be understood by a non-technical player.

**UX-SP-12: Prompt inspector is Director Mode only**  
The "Inspect Prompt" feature is gated behind Director Mode. Power users who want to see what the AI is receiving shouldn't need to enter an edit-capable mode just to read the prompt. This should be accessible separately.

### 2.3 Multiplayer UX Issues

**UX-MP-01: Room code sharing is inconvenient**  
The join URL appears as a long text hyperlink in the lobby with a tiny "copy" button. For most use cases (inviting a friend on Discord), the user must copy this link manually. There is no QR code, no "Share" button that copies a formatted invite message, no mobile share API call. For remote play over ngrok, the URL includes a long tunnel hostname that is awkward to dictate verbally.

**UX-MP-02: No turn notification**  
If a player switches tabs during their partner's turn (to chat on Discord, for example), they receive no notification when their turn arrives. There is no browser notification, no favicon badge change, no audio cue, and no title bar update (`[Your Turn] Tavern Tales`). For remote play this is a significant pain point — players must actively watch the page.

**UX-MP-03: Multiplayer play screen has no character sheet access**  
The left column is the narrative; the right column has the Roster panel (tiny) and OOC chat. There is no way to view stats, inventory, location, or lorebook in the play view. For a game that tracks these values, hiding them entirely during play is a significant regression from single-player.

**UX-MP-04: The lobby waits silently for the guest**  
After the host readies up, the screen says "Waiting for partner." but there is no clear call-to-action for what they should do next (share the join URL, wait, send a message). A "📋 Copy Join Link" button prominently placed in the waiting state would help.

**UX-MP-05: Character card draft/save model is confusing**  
In the lobby, each player edits their character in a local draft and then must click "Save Character" before the partner sees the update. There is no indication that unsaved changes exist or that the partner cannot see uncommitted edits. Players may Ready up with stale character data if they forget to save. Auto-save on input change (debounced) would be better.

**UX-MP-06: The Ready state transition is abrupt**  
When both players ready up, the lobby screen instantly switches to the play screen with no transition, no "Session starting in 3…2…1…" countdown, and no opening narration. The shift from lobby → turn 0 is jarring.

**UX-MP-07: "Prompted by [name]" attribution is easy to misread**  
NarrationBlocks label whose action prompted the response, but the label reads "Prompted by Aria" in a small badge, and the narration below is the GM's response — not Aria's action text. New players may read this as "Aria said this" rather than "this is the GM's response to Aria's action."

**UX-MP-08: Multiplayer session actions (archive, delete) lack confirmation modals**  
In the play screen, the host's "Archive" and "Delete" buttons in the header execute immediately via WebSocket message with no confirmation dialog. In single-player, all destructive actions go through the modal system. This inconsistency could result in accidental session deletion.

**UX-MP-09: Player slot labels ("host" / "guest") are shown to users**  
Throughout the UI, internal slot identifiers `host` and `guest` are surfaced: in the Roster panel ("host · you"), in NarrationBlock badges, in connection status labels. These are technical labels. The UI should use character names or display names exclusively and never show the internal slot key to the player.

**UX-MP-10: Join entry does not validate room codes against the server**  
The "Connect to Room" button enables as soon as the room code has 4+ characters, a display name, and a character name. There is no async check against the server to verify the room code exists before committing. The error only surfaces after a failed WebSocket join, which gives a generic banner message.

**UX-MP-11: The "Partner disconnected" state gives no actionable guidance**  
When a partner disconnects, the screen reads "Partner disconnected - waiting up to 5 minutes for reconnect." There is no countdown, no suggestion to "send them a message to let them know," no button to "give up and archive the session," and no guidance on what the reconnecting partner should do (they get a WebSocket error and must figure out on their own that they need to navigate back to the room).

**UX-MP-12: Multiplayer entry form has no "Back" affordance that warns about losing setup**  
If a guest fills out the join form with preferences set up and then accidentally clicks "Back," all their preference configuration is lost without warning.

---

## Section 3: Features That Need Improvement

### 3.1 High Priority

**IMP-01: Multiplayer narrative must show player actions alongside GM responses**  
Currently: only the GM's response is displayed, tagged with "Prompted by [name]."  
Needed: each NarrationBlock should include the player's declared action above the GM response, formatted differently (player's voice vs. GM voice). Players need to know what their partner actually said.

**IMP-02: Character sheet sidebar in multiplayer play**  
Both players need access to at minimum their own stats, inventory, and current location during the play session. A collapsible "My Character" panel or a tabbed sidebar (My Character / Partner's Character / Party Lorebook) would address this.

**IMP-03: WebSocket reconnect persistence**  
The reconnect loop should continue for the duration of the server's reconnect window (5 minutes), not give up after 5 attempts (~15 seconds). The reconnect delay should cap at 10–15 seconds per retry rather than stopping entirely.

**IMP-04: Visible countdown on partner disconnect**  
Show a real-time countdown ("Reconnect window: 4:32 remaining") so both players know exactly how much time remains before they lose the session's pending turn.

**IMP-05: OOC message persistence**  
OOC messages should be stored in the campaign state or a session-side log, not only in client memory. They should survive page refreshes and reconnects. A reasonable cap (100–200 messages, older messages summarized) is fine.

**IMP-06: Multiplayer opening kickoff scene**  
Before the first player takes any action, the GM should narrate an opening scene introducing the setting and both characters. This could be triggered automatically when both players ready up — similar to the single-player kickoff, but acknowledging both characters by name and establishing the shared starting situation.

**IMP-07: Turn notification mechanism**  
When it becomes a player's turn, the browser tab title should change to "[Your Turn] Tavern Tales Reborn," the favicon could pulse or change, and an optional browser notification (if permission granted) should fire. This is essential for remote play where players are also on Discord or other apps.

**IMP-08: Reroll and Continue in multiplayer**  
Both players should be able to vote to regenerate the last GM response. A simple majority (either player can request, partner must not veto within 30 seconds) would work. Continue (extend without a new action) should be available to both players.

**IMP-09: Improve "Forge Your World" new-user flow**  
Add a "Quick Start" mode: one text box (world concept), one character name, and a "Begin Adventure" button. All other settings use defaults. Advanced configuration stays available via an "Expand Setup" toggle. This would reduce time-to-first-narration from ~10 minutes to ~1 minute.

**IMP-10: Model selection clarity**  
The utility model dropdown says "(auto — falls back through llama3.1:8b → qwen2.5:7b → mistral)" which is good, but the selected state of "(auto)" and an explicitly set model look nearly identical. When set to auto, a subtle "(auto)" chip or color should distinguish it from a manually chosen model.

### 3.2 Medium Priority

**IMP-11: Multiplayer session access for guests from the main menu**  
Add a "My Sessions" list or "Rejoin by Room Code" input on the main menu for guests. Alternatively, store the last-joined room code in localStorage so the "Join Multiplayer" button pre-fills the room code on return visits.

**IMP-12: Director Mode access for both players in multiplayer**  
Both players should have limited Director Mode access to their own character's stats, inventory, and appearance. The host should retain exclusive rights to NPCs, lorebook, and the overall world state.

**IMP-13: Confirmation dialogs for multiplayer destructive actions**  
Archive and Delete in the play view should go through the same modal-confirm pattern used in single-player. This is a two-line fix but prevents data loss.

**IMP-14: Hide internal slot identifiers from the UI**  
Replace all instances of "host" and "guest" as displayed labels with character names or display names. Keep slot identifiers internal only.

**IMP-15: Campaign list cleanup — hide raw IDs**  
The campaign ID (`campaign_1746000000000`) shown in the campaign list should be hidden or replaced with a formatted creation date ("started Apr 28" or similar).

---

## Section 4: Features to Add

### 4.1 Multiplayer Additions

**ADD-MP-01: QR Code for Room Joining**  
Generate a QR code in the lobby that encodes the join URL. Mobile guests can scan it to join instantly. A "Share" button that produces a formatted invite message ("Join my Tavern Tales session! Room: WOLF42 | Link: ...") would complement this.

**ADD-MP-02: Turn Timer (Optional)**  
An optional countdown timer per turn (configurable: 2 min / 5 min / 10 min / unlimited). If the timer expires, the GM narrates a "you hesitate" response and the turn passes to the other player. This prevents sessions from stalling when one player is AFK. The host should be able to set or override this before starting.

**ADD-MP-03: Simultaneous Action Mode**  
An alternate turn mode where both players submit their action in secret, then the GM narrates a response that weaves both actions into a single coherent scene. The input field is hidden from each player until both have submitted. This is how many tabletop RPGs work (declare → resolve) and would feel dramatically different from the current strict alternation.

**ADD-MP-04: Spectator Mode**  
Allow additional connections to watch the session without acting. Spectators see the narrative and OOC chat (or a spectator-only OOC channel) but cannot submit actions. Useful for streaming or having a GM-assistant review the story.

**ADD-MP-05: Collaborative World Forge**  
A shared lobby screen where both players contribute to world creation. Player 1 writes the world concept; Player 2 writes their character; both review and approve the AI-generated world before the session starts. This replaces the current host-only setup model.

**ADD-MP-06: Inter-Character Relationship Tracking**  
Add a schema field for the relationship status between the two player characters (neutral / bonded / tense / rivalrous / romantic / etc.) that the AI is instructed to honor and the players can see and optionally edit in Director Mode.

**ADD-MP-07: Host-to-Guest Session Transfer**  
If the host needs to leave, they can transfer host rights to the guest. The session persists and the new host can continue managing it. Currently, if the host leaves, the guest is stranded.

**ADD-MP-08: Shared Action Queue / Party Decision Mode**  
For scenes that require a party decision (e.g., "which path do we take?"), the GM could pose a question and both players vote. Majority decides; the AI narrates the outcome. An in-game vote button would make this natural.

**ADD-MP-09: Per-Turn Action Log in Sidebar**  
A turn-by-turn log in the right sidebar showing: Turn #, [Character Name] — "[their action text]" → result. This gives both players a scannable history of who did what without scrolling through the narrative.

**ADD-MP-10: Session Transcript Export**  
Export the full session as a formatted, readable document: alternating player actions and GM narration, timestamped, with character names. Output as Markdown or plain text for easy sharing or archiving. Include OOC messages in a separate appendix if desired.

### 4.2 General Additions

**ADD-GEN-01: NPC Portrait Generation**  
Integrate an optional local image-generation call (Stable Diffusion via ComfyUI or similar) to generate portrait thumbnails for NPCs when they are introduced. Display these as small circular avatars in the Cast sidebar. The AI can generate a concise prompt from the NPC's appearance field. Make it entirely optional and off by default.

**ADD-GEN-02: World Map / Location Graph**  
A simple auto-generated node graph showing locations the player has visited, connected by how they traveled between them. The map would update as the AI describes movement to new locations. Does not need to be a pixel-art map — a network graph of named nodes with a brief scene label would add significant immersion.

**ADD-GEN-03: Audio Turn Notification & Ambient Sound**  
An optional audio layer: a brief chime when it's the player's turn, and selectable ambient loops (tavern noise, forest sounds, dungeon drips) that play quietly in the background. Both should be individually toggle-able and volume-controlled.

**ADD-GEN-04: "Quick Start" World Templates**  
Pre-built world templates (High Fantasy, Gritty Dark Fantasy, Sci-Fi, Horror, Historical, Modern Paranormal) that pre-fill the world description, lorebook, and a starting NPC or two. Players can customize from there. Dramatically reduces setup time and gives newcomers a guided starting point.

**ADD-GEN-05: Inline Dice Roller UI**  
A prominent "Roll" button in the input area that opens a small popover: select attribute + action type → see the dice roll context (the d20 result, the modifier, the DC) in a styled panel before the GM narration begins. Currently the roll happens silently in the backend and the result only appears as a small badge. Making it theatrical — showing the die result as a card — would add excitement.

**ADD-GEN-06: Story Bookmarks**  
Players can bookmark specific turns with a tag ("first meeting with Elena," "the betrayal at the gate"). Bookmarks appear in a panel and clicking one scrolls to that point in the narrative. In multiplayer, both players share bookmarks.

**ADD-GEN-07: Session Templates / Scenario Packs**  
Pre-written campaign seeds (a village mystery, a dungeon run, a ship heist) with pre-populated lorebook, NPCs, and starting scene. A player can pick a template and the world forge pre-fills all fields. This is the fastest possible path from "open app" to "playing."

**ADD-GEN-08: Chapter Summary View**  
The summarizer already generates short, chapter, and arc summaries. These are currently invisible to the player unless they inspect the raw state. A "Story So Far" panel or collapsible section in the sidebar that shows the current summaries at each level would make the auto-summary feature visible and useful.

**ADD-GEN-09: Preference Profile Linking from Campaign View**  
The active preference profile is shown in the sidebar as a small green box. Clicking it should open the Preference Profiles editor in a modal (or navigate to it), allowing the player to review or adjust their preferences mid-campaign without navigating away. Currently there is no in-game link to the profile editor.

**ADD-GEN-10: Action Input Auto-Grow**  
The action textarea has `rows={1}` with `max-h-40 resize-y`. It does not auto-grow as the player types multi-paragraph actions. The resize handle is small. The textarea should auto-expand to content height up to the max, without requiring manual drag.

**ADD-GEN-11: Mobile-Optimized Play View**  
The current layout is designed for desktop (sidebar on left, narrative on right). On mobile, the sidebar is hidden behind a "State" toggle. Consider a bottom-sheet pattern for mobile: narrative full-width, a swipe-up panel for stats/cast/lorebook, and the input anchored to the bottom of the screen. The multiplayer layout (`lg:grid-cols-[3fr_1fr]`) stacks poorly on mobile — the OOC panel and roster end up below the entire narrative scroll area.

**ADD-GEN-12: Persistent Campaign Journal / Notes**  
A freeform notes field attached to the campaign (not the lorebook — that is AI-facing). This is a scratchpad for the player's own use: theories, planned actions, NPC notes they've inferred. Completely hidden from the AI.

---

## Section 5: Additional Recommended Improvements

### 5.1 Session Continuity & Stability

**REC-01: Graceful Ollama restart handling**  
If Ollama goes down mid-streaming (the player's local machine is resource-constrained), the stream breaks with a generic fetch error. The frontend should detect a broken stream and offer a retry or at least explain the likely cause. The partial content should be preserved in the UI rather than disappearing.

**REC-02: Multiplayer session recovery from generating state on server restart**  
If the server restarts during GENERATING (mid-AI-turn), the session comes back in PAUSED state with `paused_status_before = GENERATING`. On reconnect, `_maybe_resume_from_pause` would try to restore GENERATING status — but there is no running generation task. The session would appear to be generating forever. The recovery path should detect a GENERATING-before-pause condition and advance to the next turn's slot instead.

**REC-03: Rate limit feedback**  
The 60 req/min rate limiter returns a 429, which the frontend turns into a banner error. The error message should include "Please wait a moment" and ideally show the retry-after duration if the backend surfaces it.

**REC-04: Campaign state version migration path**  
The CLAUDE.md notes that schema v2 does not migrate from v1. This is acceptable for now but should be documented prominently in the UI ("Your old campaigns from v1 are not compatible — please start new ones") rather than silently logging a warning on startup that users never see.

### 5.2 Preference System Improvements

**REC-05: Preference profile "active for this campaign" indicator in editor**  
In the Preference Profiles manager, there is no visual indication of which profile is linked to which campaign. A "used in: Campaign Name" chip on each profile would help players track which profiles are active.

**REC-06: Quick preference setup should offer profile save**  
The multiplayer Quick Preference Setup creates a temporary profile that is used for the session but never saved. A "Save this as a profile" button on the Quick Setup results screen would make it easy to reuse settings without needing the full editor.

**REC-07: Preference merge preview before readying up**  
Currently the merged preference summary only appears in the lobby after both players have joined. Players cannot preview what the merge will look like until they are already in the session. A preview step during the Quick Setup ("If your partner has similar preferences, the session would allow: [list]") would help set expectations.

**REC-08: Preference profile onboarding wizard is not discoverable**  
The 5-step onboarding wizard inside the Preference Profiles screen is excellent but only accessible after navigating away from the main menu. First-time users who skip preference setup have no indication they are missing a significant system. A gentle "Set up your RP preferences?" nudge on the main menu would help.

### 5.3 Performance & Technical

**REC-09: Narrative scroll anchoring during streaming**  
During streaming, the scroll anchor (`scrollAnchorRef`) sits at the bottom of the message list. As tokens arrive and the GM message block grows, the page should auto-scroll to keep the latest text visible. Currently the anchor is placed correctly but whether smooth continuous scrolling works during streaming depends on the browser's behavior with the growing element — worth explicit testing and possibly a `MutationObserver` pattern.

**REC-10: Memory store error isolation**  
ChromaDB errors currently propagate through the chat handler. If the vector store becomes corrupted or the segment directory is in a bad state, chat will fail entirely. The memory retrieval and write steps should be wrapped in `try/except` with a fallback to "no memories this turn" rather than surfacing a 500 to the user.

**REC-11: Summarizer should be configurable per-campaign**  
The summarization cadence (short @ 5 turns, chapter @ 20, arc when >5 chapters) is global and hardcoded. Some players run short sprint sessions of 10 turns; others run 200-turn sagas. Surfacing these thresholds as campaign settings (even just short/medium/long cadence presets) would improve flexibility.

**REC-12: Cleanup expired sessions periodically**  
`cleanup_expired_sessions()` exists in the session manager but there is no evidence it is scheduled to run. If it is only called manually, sessions older than 24h will accumulate in memory. A background task registered during FastAPI startup (or a nightly cron via apscheduler) would keep the runtime tidy.

### 5.4 Accessibility

**REC-13: Keyboard navigation in the main menu**  
Campaign cards in the main menu have no visible keyboard focus ring. Tab order jumps unpredictably between rename input, rename button, host button, and delete button. Full keyboard navigation with proper focus management would make the app usable without a mouse.

**REC-14: Screen reader support for streaming narration**  
The streaming text area uses `aria-hidden="true"` on the scroll anchor but does not declare the message list as an `aria-live` region. Screen readers will not announce incoming narration tokens. Adding `aria-live="polite"` to the assistant message container would announce completed responses.

**REC-15: Color-only indicators have no text fallbacks**  
Connection status dots (green = connected, red = disconnected) are color-only. Adding a text label ("●  Connected / ● Disconnected") or a visually-hidden SR-only label would make these accessible to color-blind users.

---

## Priority Matrix Summary

| Priority | Item | Area |
|----------|------|------|
| Critical | F-MP-01: No multiplayer kickoff scene | Multiplayer |
| Critical | F-MP-02: No character stats in multiplayer play | Multiplayer |
| Critical | F-MP-03: Player actions not shown in narrative | Multiplayer |
| Critical | F-MP-04: WebSocket reconnect gives up too soon | Multiplayer |
| Critical | UX-MP-03: No character sheet during play | Multiplayer |
| High | F-MP-07: Fixed host-first turn order | Multiplayer |
| High | F-MP-08: No Reroll/Continue in multiplayer | Multiplayer |
| High | UX-MP-01: Room code sharing is inconvenient | Multiplayer |
| High | UX-MP-02: No turn notification | Multiplayer |
| High | UX-MP-08: No confirmation on destructive actions | Multiplayer |
| High | IMP-09: Quick Start world setup | General |
| High | ADD-MP-01: QR code / share button | Multiplayer |
| High | ADD-MP-02: Turn timer option | Multiplayer |
| High | ADD-MP-09: Per-turn action log | Multiplayer |
| High | ADD-MP-10: Session transcript export | Multiplayer |
| Medium | F-MP-06: OOC messages ephemeral | Multiplayer |
| Medium | F-MP-10: No return to single-player path | Multiplayer |
| Medium | F-MP-12: Host-only world creation | Multiplayer |
| Medium | UX-SP-01: "Commit" label | General |
| Medium | UX-SP-02: No first-run onboarding | General |
| Medium | UX-SP-07: Roll result placement | General |
| Medium | ADD-GEN-01: NPC portrait generation | General |
| Medium | ADD-GEN-04: World templates | General |
| Medium | ADD-GEN-05: Inline dice roller UI | General |
| Medium | ADD-GEN-08: Chapter summary view | General |
| Low | ADD-GEN-02: World map / location graph | General |
| Low | ADD-GEN-03: Ambient sound | General |
| Low | ADD-GEN-06: Story bookmarks | General |
| Low | ADD-GEN-12: Player journal/notes | General |
| Low | REC-13–15: Accessibility | General |

---

## Closing Notes

The foundation is genuinely impressive — the prompt engine, preference system, state extraction, and WebSocket architecture are each more sophisticated than most open-source projects in this space. The single-player experience is close to feature-complete. The multiplayer experience has the architecture but not yet the UX.

The most impactful single change would be **showing player-submitted action text alongside GM narration in the multiplayer view** — without that, collaborative storytelling is opaque and the experience feels like watching an unknown author's work rather than co-authoring a story. The second most impactful would be **a character sheet panel in the multiplayer play view** — players can't engage with stat-driven mechanics if they can't see their stats.

Everything else listed here is incremental improvement on top of a solid core.

---

## Developer Notes — Rejected & Deferred Items

*This section was added by the lead developer during implementation planning. The following suggestions from the QA evaluation were reviewed and either rejected outright or deferred beyond v2 scope. The rationale for each decision is included so it can be revisited in a future planning cycle.*

---

### REJECTED: Collaborative World Forge (F-MP-12 / ADD-MP-05)

**QA suggestion:** A shared pre-game lobby where both players co-author the world before the campaign is created. Both players contribute to the world concept, character setup, and starting scene together in real time.

**Developer decision: REJECTED for v2. Deferred to v3 consideration.**

**Rationale:** The current architecture creates the campaign first and then attaches a multiplayer session. Implementing a shared world-building step before campaign initialization would require:
- A new ephemeral "pre-session" WebSocket channel that operates before any campaign ID exists
- A collaborative editing model (operational transforms or last-writer-wins) for the world forge form
- A new server-side state for "pending world" that is not persisted as a campaign until both players agree
- Complete rework of the `CampaignCreator` flow

This represents a major new surface area that would delay the critical multiplayer fixes (Epics 3 and 4) by several sprints. The current host-only setup model is not ideal UX, but it is functional and not a blocker. Story 3.9 (lobby polish) partially addresses this by making the lobby more welcoming to guests, and the guest character card editor in the lobby lets guests customize their character before play begins.

---

### REJECTED: Guest Editing Partner's Character (F-MP-13)

**QA suggestion:** In the lobby, guests should be able to suggest edits to the host's character card.

**Developer decision: REJECTED — by design.**

**Rationale:** Character ownership is intentional. Each player owns their own character and should not be able to modify their partner's character without explicit consent. Allowing cross-character editing introduces potential for grief play and undermines the consent-first philosophy already embedded in the preference system. The multiplayer Director Mode (Story 3.4) gives each player control over their own stats, which is the appropriate scope. If collaborative character editing is desired in a specific campaign, it should be done verbally between players and then each player updates their own card.

---

### REJECTED: Party Decision Vote Mode (ADD-MP-08)

**QA suggestion:** A dedicated in-game voting system where the GM poses a binary question and both players vote, with the majority outcome narrated by the AI.

**Developer decision: REJECTED — superseded by Simultaneous Action Mode (Story 4.4).**

**Rationale:** Simultaneous Action Mode (ADD-MP-03 → Story 4.4) addresses the underlying use case more completely. If the GM poses a fork in the road and both players submit "We go left" / "We go right," the AI narrates a scene that addresses the tension or resolves it (perhaps they argue and then reach a consensus). A formalized voting system would be a separate UI construct on top of this and would feel mechanical compared to letting the narrative handle it. Adding both would create two overlapping "special modes" that confuse players about which to use. Simultaneous Action Mode is the correct general solution.

---

### REJECTED: Schema v1 → v2 Migration (REC-04)

**QA suggestion:** Instead of silently logging a warning when old v1 campaigns are found on startup, prominently inform users in the UI that their v1 campaigns are not compatible.

**Developer decision: PARTIALLY REJECTED — the UI notice is accepted but formal migration tooling is not.**

**Rationale:** The v1 → v2 migration was explicitly ruled out of scope during the original architecture audit (AUDIT_REPORT.md). The shape differences between v1 and v2 (different field names, different NPC schema, missing enum types) make a safe automated migration risky — a bad migration that silently corrupts state data is worse than no migration. The accepted portion (REC-04) is limited to: on server startup, if a `backend/campaign_states.json` (v1) file is detected, a warning should be logged AND a `GET /api/health` response should include `{ "legacy_campaigns_detected": true }` which the frontend can use to show a one-time banner to the user. No migration of the actual data.

---

### DEFERRED: NPC Portrait Generation (ADD-GEN-01)

**QA suggestion:** Integrate a local image-generation service (Stable Diffusion via ComfyUI or similar) to generate portrait thumbnails for NPCs when they are introduced.

**Developer decision: DEFERRED — out of scope for v2. Post-v2 optional plugin.**

**Rationale:** This feature requires users to have a separate image generation service (Stable Diffusion + ComfyUI, or AUTOMATIC1111) installed and running locally, in addition to Ollama. This represents a significant additional system requirement that many users will not be able or willing to satisfy. The integration surface — sending prompts to an external service, handling image formats, displaying images in the sidebar — is non-trivial and would require ongoing maintenance as Stable Diffusion APIs change.

The feature has genuine appeal (portraits would elevate immersion significantly) and should be revisited as a plugin or optional integration *after* the core v2 improvements are shipped. At that point, it can be designed as a clearly optional feature with its own setup documentation, enabled via a settings flag, and with graceful fallback when the image service is unavailable.
