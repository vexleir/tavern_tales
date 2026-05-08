# Fantasy Creator — Implementation Plan

A couples roleplay fantasy generator built on top of the existing preference profile system.
Takes two profiles + guided scene questions → produces a structured real-world fantasy with
narrative, per-person roles, props, mood tips, scripted dialogue, aftercare, and safety tooling.

---

## What Already Exists (Do Not Rebuild)

| Capability | Location |
|---|---|
| Encrypted profile storage (Fernet AES-128) | `secure_storage.py`, `preference_store.py` |
| Password-protected fantasy documents (PBKDF2) | `secure_storage.py` → `password_encrypt_text` |
| Profile export/import JSON endpoints | `main.py`, `preference_store.py` |
| Two-profile comparison + veto merging | `preference_logic.py`, `preference_merger.py` |
| Fantasy generation (template-based) | `preference_logic.py` → `build_overlap_fantasy` |
| `GeneratedFantasy` schema | `preference_schema.py` |
| Profile management UI | `frontend/src/PreferenceProfiles.jsx` |

The gap: profile exports are **not password-protected at the file level**; fantasy generation is
**template-based** (no AI narrative); there is **no guided scene questionnaire**; the structured
output fields (roles, props, script, aftercare, safe words, negotiation checklist) **do not exist**.

---

## Phases

### Phase 1 — Password-Protected Profile Export/Import
**Estimated effort: 1–2 days**

Profile files need to be shareable between partners on different machines without exposing
preference data in plaintext.

#### Backend

**`secure_storage.py`** — add two functions that reuse the existing PBKDF2 path:
```python
def password_encrypt_payload(payload: dict, password: str) -> dict
    # wraps the JSON payload with the same PBKDF2+Fernet envelope used for fantasy content

def password_decrypt_payload(envelope: dict, password: str) -> dict
    # inverse; raises ValueError on bad password
```

**`preference_store.py`** — add:
```python
async def export_profile_with_password(profile_id: str, password: str, include_private: bool) -> dict
    # loads the profile, redacts if needed, then password_encrypt_payload wraps the export dict
```

**`main.py`** — update routes:
- `GET /api/preference-profiles/{id}/export` → accept optional `password` query param; when
  provided, call `export_profile_with_password` and set the envelope's `passwordProtected: true`
  header field so the client knows it needs a password to import.
- `POST /api/preference-profiles/import` → accept optional `password` field in the request body;
  detect `passwordProtected: true` in the payload before calling `import_profile`, decrypt first.

#### Frontend (`PreferenceProfiles.jsx`)

- Export dialog: add "Password protect this export?" toggle. When toggled, show a password +
  confirm field. Send password to the export endpoint.
- Import flow: after the user picks a file, peek at the JSON for `passwordProtected: true`.
  If present, show a password prompt before posting to `/import`.

---

### Phase 2 — Scene Questionnaire System
**Estimated effort: 1 day**

A structured questionnaire that determines the fantasy's archetype, setting, tone, and pacing
before generation. Answers are stored on the fantasy so it can be regenerated consistently.

#### Backend — new file `scene_questionnaire.py`

```python
class ArchetypeType(str, Enum):
    ROMANTIC        = "romantic"        # sensual, intimate, tender
    PLAYFUL         = "playful"         # fun, teasing, comedic
    POWER_EXCHANGE  = "power_exchange"  # D/s, authority, protocol
    TABOO_LIGHT     = "taboo_light"     # forbidden/secret, mild transgression
    CNC             = "cnc"             # consensual non-consent
    DARK            = "dark"            # psychological, fear-as-play

class SceneQuestionnaire(BaseModel):
    archetype: ArchetypeType
    setting: str            # "domestic" | "professional" | "fantasy" | "outdoor" | "hotel" | custom
    tone: str               # "tender" | "playful" | "intense" | "serious"
    pacing: str             # "slow_burn" | "direct" | "escalating"
    intensityOverride: IntensityPreference | None = None
    includeAftercare: bool = True
    includeSafeWords: bool = True
    personAAlias: str = "Person A"
    personBAlias: str = "Person B"

def map_questionnaire_to_prompt_params(q: SceneQuestionnaire, merged_context: dict) -> dict:
    # Returns generation parameters: intensity ceiling, required_safe_word_placement,
    # aftercare_tier, tone_directives, setting_description
```

Archetype → safety escalation mapping (used by generator):

| Archetype | Aftercare tier | Safe word in script | Consent banner prominence |
|---|---|---|---|
| ROMANTIC | optional | optional | standard |
| PLAYFUL | optional | optional | standard |
| POWER_EXCHANGE | recommended | recommended | elevated |
| TABOO_LIGHT | recommended | recommended | elevated |
| CNC | required | required (at act breaks) | prominent |
| DARK | required | required (at act breaks) | prominent |

---

### Phase 3 — Extended Fantasy Schema
**Estimated effort: 1 day**

All new fields are optional with empty-list defaults so existing stored fantasies remain valid.

#### `preference_schema.py` — add new models and extend `GeneratedFantasy`

```python
class FantasyRole(BaseModel):
    personAlias: str
    roleName: str                      # e.g., "The Strict Professor"
    characterDescription: str          # who this character is in the scene
    guidance: str                      # how to play this role
    powerPosition: str | None = None   # "dominant" | "submissive" | "switch" | "neutral"

class FantasyProp(BaseModel):
    item: str
    tier: Literal["required", "nice_to_have", "advanced"]
    note: str | None = None
    sensitive: bool = False            # True if the prop is kink-specific

class MoodTip(BaseModel):
    category: Literal["ambiance", "sensory", "timing", "apparel", "digital"]
    tip: str

class ScriptLine(BaseModel):
    speaker: str                       # personAlias | "narrator" | "both"
    lineType: Literal["action", "dialogue", "direction"]
    text: str
    note: str | None = None            # director note, e.g., "pause here"

class ScriptPhase(BaseModel):
    phaseName: str                     # e.g., "Opening", "Rising Tension", "Peak", "Cooldown"
    phaseType: Literal["opening", "rising", "peak", "aftercare"]
    lines: list[ScriptLine]

class AftercareSuggestion(BaseModel):
    timing: Literal["immediate", "within_hour", "next_day"]
    suggestion: str

class NegotiationItem(BaseModel):
    topic: str
    question: str
    priority: Literal["must_discuss", "recommended", "optional"]
    context: str | None = None

class SafeWordRecommendation(BaseModel):
    word: str
    gesture: str | None = None
    useCase: str

class DebriefQuestion(BaseModel):
    question: str
    category: str                      # "emotional" | "physical" | "roleplay" | "next_time"

# New optional fields on GeneratedFantasy:
roles: list[FantasyRole] = []
props: list[FantasyProp] = []
moodTips: list[MoodTip] = []
scriptPhases: list[ScriptPhase] = []
aftercareGuide: list[AftercareSuggestion] = []
safeWordRecommendations: list[SafeWordRecommendation] = []
negotiationChecklist: list[NegotiationItem] = []
debriefTemplate: list[DebriefQuestion] = []
compatibilityScore: float | None = None       # matched_items / total_comparable_items
sceneQuestionnaire: SceneQuestionnaire | None = None
toneVariantIds: list[str] = []               # IDs of lighter/darker variants of this fantasy
```

---

### Phase 4 — AI-Driven Fantasy Generation
**Estimated effort: 3 days**

Replace the template-based `_compose_content` / `_compose_synopsis` approach with Ollama-driven
generation that produces the full structured output.

#### Backend — new file `fantasy_generator.py`

Primary function:
```python
async def generate_structured_fantasy(
    merged_context: CampaignPreferenceContext,
    questionnaire: SceneQuestionnaire,
    comparison: dict,           # from compare_profiles; supplies negotiation items
    ollama_url: str,
    model: str,
    utility_model: str,
) -> GeneratedFantasy
```

Internal pipeline:
1. **Negotiation checklist** — derived from `comparison["blocked"]` (soft_no / discuss_only items
   become `must_discuss`; `maybe` items become `recommended`). Rule-based, no AI needed.
2. **Safe word recommendations** — rule-based from archetype. ROMANTIC/PLAYFUL get one suggested
   word. POWER_EXCHANGE/TABOO_LIGHT get word + gesture. CNC/DARK get two words (pause + stop)
   + gesture, placed at each act break in the script.
3. **Aftercare guide** — rule-based from archetype + intensity. Light/moderate non-CNC: 2–3 items.
   Power exchange: 4–5 items. CNC/Dark: 6–8 items, always includes "immediate" tier entries.
4. **Debrief template** — mostly static; 4 questions for ROMANTIC/PLAYFUL, 6 for POWER_EXCHANGE,
   8 for CNC/DARK (adds emotional processing questions).
5. **AI generation call** — single Ollama call with a structured JSON-output prompt:
   - System prompt instructs the model to output a specific JSON schema (roles, props, moodTips,
     scriptPhases, synopsis, title).
   - User message contains: merged themes, questionnaire answers, aliases, intensity, archetype,
     setting, tone, pacing, consent framing.
   - Uses `ollama_client` non-streaming call with temperature 0.85, top_p 0.9.
6. **Validation + repair** — parse AI JSON output, validate with Pydantic, fill missing fields
   with safe defaults, log any repair actions.
7. **Compatibility score** — `len(matched_items) / max(1, len(matched_items) + len(blocked_items))`.

**`prompt_templates.py`** — add `FANTASY_GENERATOR_SYSTEM_PROMPT`:
- Instructs the model to output valid JSON matching the fantasy schema.
- Describes each output field with examples.
- Embeds the safety principle: "This is a consensual fantasy between adults. Fantasy interest
  is not real-world consent."
- For CNC/Dark archetypes: additional directive to embed safe word markers at act breaks.

**`main.py`** — new routes:
```
POST /api/fantasy-creator/generate
    Body: { firstProfileId, secondProfileId, questionnaire: SceneQuestionnaire, save: bool }
    Returns: GeneratedFantasy (with all structured fields populated)

POST /api/fantasy-creator/generate-variant
    Body: { fantasyId, variantTone: "lighter" | "darker" }
    Returns: GeneratedFantasy (new fantasy with toneVariantIds cross-linked)
```

---

### Phase 5 — Fantasy Creator UI
**Estimated effort: 3 days**

New React component `frontend/src/FantasyCreator.jsx` with a 5-step wizard and a rich output
display. Integrated into the main app navigation.

#### Step 1 — Profile Selection

- "Your Profile" — dropdown of existing profiles.
- "Partner Profile" — two options:
  - Select from previously imported profiles (filtered to show `(Imported)` profiles).
  - Import a new partner profile file → detects `passwordProtected: true`, prompts for password
    before sending to `/api/preference-profiles/import`.
- "Person A alias" and "Person B alias" text fields (pre-filled from profile display names,
  editable so partners can use scene names / pseudonyms).

#### Step 2 — Compatibility Overview

Auto-fetches comparison on profile pair selection. Displays:
- **Compatibility score** — circular gauge (e.g., "72% match"). Shows matched / total items.
- **Matched themes** — top 5 items with fantasy interest and intensity pills.
- **Discuss first** — items where either profile has `maybe` or `discuss_only`. Shown with a
  yellow "chat bubble" icon. These feed the negotiation checklist.
- **Not included** — hard blocks listed by label only (no details to preserve privacy).
- Proceed button enabled when at least 1 matched theme exists.

#### Step 3 — Scene Questionnaire

- **Archetype cards** — 6 cards with icon, label, and 1-sentence description. Selecting a
  CNC or Dark card shows a brief consent acknowledgement the user must confirm.
- **Setting** — pill selector: Domestic / Professional / Fantasy / Outdoor / Hotel / Custom.
  Custom shows a text field.
- **Tone slider** — labeled axis: Tender ←→ Playful ←→ Intense ←→ Serious.
- **Pacing** — 3-option toggle: Slow Burn / Direct / Escalating.
- **Intensity** — optional override (defaults to merged profile intensity ceiling).
- **Safety toggles** — "Include aftercare guide" (default on) and "Include safe word suggestions"
  (default on; locked to on for CNC/Dark archetypes).

#### Step 4 — Generation

- "Generating your fantasy…" loading state with phase labels:
  - "Building compatibility checklist…"
  - "Crafting roles and setting…"
  - "Writing the script…"
  - "Adding finishing touches…"
- On error: inline error with "Try again" button.

#### Step 5 — Fantasy Output

Tabbed layout:

| Tab | Contents |
|---|---|
| **Story** | Title (editable), synopsis, full narrative content (editable) |
| **Roles** | Card per person: role name, character description, how-to-play guidance, power position badge |
| **Script** | Phase headers (Opening / Rising / Peak / Cooldown), color-coded lines by speaker, action vs. dialogue labels, safe word markers highlighted in amber |
| **Prep** | Props table (Required / Nice to Have / Advanced tiers, sensitive props opt-in revealed); Mood tips by category |
| **Safety** | Pre-scene negotiation checklist (must-discuss items highlighted, cannot be collapsed on first view); Safe word recommendations |
| **Aftercare** | Aftercare suggestions by timing (Immediately / Within the hour / Next day); Debrief questions |

Action bar:
- Save fantasy
- Print view (clean print-formatted layout, all tabs combined)
- Generate lighter / darker variant
- Create Tavern Tales campaign from this fantasy (routes to existing campaign creation)
- Export with sharing mode picker

#### `App.jsx` integration

- Add "Fantasy Creator" entry to main navigation alongside "Campaigns" and "Profiles".
- `FantasyCreator` mounts as a top-level view (not nested in `PreferenceProfiles`).

---

### Phase 6 — Safety Integration
**Estimated effort: 1 day**

Ensure responsible framing is present, prominent, and not dismissable for high-intensity content.

#### Rules

1. **Universal consent banner** — every generated fantasy output begins with:
   > *"This is a consensual fantasy between adults. All content represents fictional scenarios.
   > Fantasy interest is not real-world consent."*
   Displayed as a styled banner above the Story tab, not a modal that can be skipped.

2. **CNC / Dark archetype gate** — on selecting CNC or Dark in the questionnaire, display a
   brief acknowledgement checkbox: "I understand this scene involves simulated non-consent and
   both participants have agreed to engage in this fantasy." Generation is blocked until checked.

3. **Script safe word placement** — for CNC/Dark: `fantasy_generator.py` embeds `[SAFE WORD CHECK]`
   markers in the script at each phase transition. The UI renders these as amber callout boxes
   with the agreed safe words printed inside.

4. **Negotiation checklist auto-expand** — the Safety tab's checklist accordion is expanded by
   default on first load. `must_discuss` items have a red badge. The tab itself shows a badge
   count of must-discuss items in the tab header.

5. **Aftercare first for intense content** — for POWER_EXCHANGE, CNC, Dark archetypes, the
   Aftercare tab is shown as the second tab (after Story) rather than last, and a reminder
   appears at the bottom of the Script tab: "Aftercare guidance is available in the Aftercare tab."

6. **Debrief template always present** for POWER_EXCHANGE, CNC, Dark archetypes — the tab is
   always visible and cannot be removed from the output.

---

## File Change Summary

| File | Change type | Notes |
|---|---|---|
| `backend/secure_storage.py` | Modify | Add `password_encrypt_payload`, `password_decrypt_payload` |
| `backend/preference_store.py` | Modify | Add `export_profile_with_password` |
| `backend/preference_schema.py` | Modify | Add 8 new models; extend `GeneratedFantasy` |
| `backend/scene_questionnaire.py` | **New** | Questionnaire schema + param mapping |
| `backend/fantasy_generator.py` | **New** | AI generation pipeline |
| `backend/prompt_templates.py` | Modify | Add `FANTASY_GENERATOR_SYSTEM_PROMPT` |
| `backend/main.py` | Modify | Update export/import routes; add `/fantasy-creator/*` routes |
| `frontend/src/FantasyCreator.jsx` | **New** | 5-step wizard + output display |
| `frontend/src/App.jsx` | Modify | Add Fantasy Creator nav entry |
| `frontend/src/PreferenceProfiles.jsx` | Modify | Add password dialogs to export/import |

**New files: 2 | Modified files: 8 | Estimated total effort: 10–12 days**

---

## Suggested Build Order

1. Phase 3 (schema) — unblocks everything else; no dependencies.
2. Phase 1 (password export/import) — standalone; can be tested immediately with existing UI.
3. Phase 2 (questionnaire) — needed by Phase 4; short.
4. Phase 6 rules for `fantasy_generator.py` (negotiation checklist, safe words, aftercare,
   debrief) — these are rule-based and can be written and tested before the AI call is wired up.
5. Phase 4 (AI generation) — the Ollama prompt + JSON parsing; the largest technical risk.
6. Phase 5 (UI) — can begin in parallel with Phase 4 using a mocked generation response.
7. Phase 6 UI rules — wired in during Phase 5, finalised last.

---

## Open Questions for Alignment Before Build

1. **Aliases in script** — should person aliases carry through into every generated script line,
   or should the AI invent character names (e.g., "Mr. Hayes" rather than "Person A")?  
   *Recommendation: use aliases everywhere; character name is part of the role card, not the script speaker label.*

2. **Variant generation** — should tone variants be auto-generated at creation time (2 calls),
   or on-demand via the "Generate lighter / darker variant" button?  
   *Recommendation: on-demand to keep generation fast.*

3. **Profile privacy on import** — when Person B imports their profile for pairing, should their
   full preference data be visible to Person A's device, or only the overlap result?  
   *Recommendation: only the overlap is used for generation; Person B's raw profile is stored
   locally and never surfaced to Person A's UI.*

4. **Streaming vs. single response** — should generation stream tokens to the UI (like chat),
   or wait for the full structured JSON before displaying?  
   *Recommendation: wait for full JSON; streaming a JSON blob mid-parse is awkward. Show
   progress phase labels instead.*

5. **Fantasy ownership** — when a fantasy is generated from two profiles, who "owns" it?
   The current schema pins `ownerProfileId` to one profile.  
   *Recommendation: pin to Person A (initiator); add `secondProfileId` as a non-nullable new
   field on the extended schema.*
