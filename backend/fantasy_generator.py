"""Fantasy Creator — AI + rule-based generation pipeline.

The high-level flow is:

  1. Compare the two profiles (preference_logic.compare_profiles).
  2. Run the merger to derive an intensity ceiling and themes safe for use.
  3. Translate the questionnaire into prompt directives + safety policy.
  4. Build the rule-based portions: negotiation checklist, safe-word recs,
     aftercare guide, debrief template. These don't need AI and must be
     correct on every run.
  5. Ask the configured Ollama model to produce the narrative portions
     (title, synopsis, content, roles, props, mood tips, script phases) as
     structured JSON.
  6. Validate, repair, and assemble a GeneratedFantasy.
"""

from __future__ import annotations

import logging
from typing import Any

from ollama_client import complete_json_detail
from preference_logic import (
    FANTASY_RANK,
    INTENSITY_RANK,
    build_preference_snapshot,
    compare_profiles,
    iter_items,
)
from preference_merger import merge_preferences
from preference_schema import (
    AftercareSuggestion,
    ArchetypeType,
    CampaignSeed,
    ContextType,
    DebriefQuestion,
    FantasyProp,
    FantasyRole,
    GeneratedFantasy,
    IntensityPreference,
    MoodTip,
    NegotiationItem,
    SafeWordRecommendation,
    SceneQuestionnaire,
    ScriptLine,
    ScriptPhase,
    SharingMode,
    UserPreferenceProfile,
    now_iso,
)
from scene_questionnaire import (
    ARCHETYPE_DESCRIPTIONS,
    map_questionnaire_to_prompt_params,
    policy_for,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule-based pieces (deterministic, always correct)
# ---------------------------------------------------------------------------


def build_negotiation_checklist(
    comparison: dict[str, Any],
    questionnaire: SceneQuestionnaire,
) -> list[NegotiationItem]:
    """Translate blocked / soft-caution items from the comparison into a
    pre-scene checklist. Items either profile flagged as `discuss_only` or
    `maybe` show up here, prioritised by how restrictive the response was.
    """
    items: list[NegotiationItem] = []

    # Hard items always come up at least as recommended discussion.
    for blocked in comparison.get("blocked", []):
        reasons = blocked.get("reasons", [])
        priority = "must_discuss" if "context_not_shared" in reasons or "fantasy_interest_not_mutual" in reasons else "recommended"
        items.append(NegotiationItem(
            topic=blocked.get("label", "Theme"),
            question=f"How should we handle '{blocked.get('label', 'this theme')}' — keep it out of scope, or discuss before reintroducing?",
            priority=priority,
            context="; ".join(reasons),
        ))

    # Matched items where either profile signaled real-world hesitation.
    for match in comparison.get("matches", []):
        rw = match.get("realWorldWillingness")
        if rw in {"discuss_only", "maybe", "soft_no"}:
            priority = "must_discuss" if rw == "soft_no" else "recommended"
            items.append(NegotiationItem(
                topic=match.get("label", "Theme"),
                question=f"For '{match.get('label', 'this theme')}', confirm together what real-world version (if any) is on the table.",
                priority=priority,
                context=f"Real-world willingness on file: {rw}",
            ))

    # Always include the universal safety topics, scaled by archetype.
    items.append(NegotiationItem(
        topic="Safe words & gestures",
        question="Agree on a pause word, a stop word, and a non-verbal stop signal. Where will each be used?",
        priority="must_discuss",
        context="Required regardless of archetype; non-verbal needed if speech is part of the scene.",
    ))
    items.append(NegotiationItem(
        topic="After the scene",
        question="What does each of you want immediately after — quiet co-presence, conversation, food, sleep?",
        priority="recommended",
        context="Aftercare needs differ between people and between scenes.",
    ))
    if questionnaire.archetype in {ArchetypeType.CNC, ArchetypeType.DARK, ArchetypeType.POWER_EXCHANGE, ArchetypeType.TABOO_LIGHT}:
        items.append(NegotiationItem(
            topic="Hard limits for tonight",
            question="State today's hard limits explicitly, even if they appear on the profile. Mood and capacity vary day to day.",
            priority="must_discuss",
            context="Profile data is a baseline, not a green light.",
        ))
    if questionnaire.archetype in {ArchetypeType.CNC, ArchetypeType.DARK}:
        items.append(NegotiationItem(
            topic="Reality anchor",
            question="Agree on a phrase that breaks character entirely — different from a safe word — for moments either of you wants the fiction off.",
            priority="must_discuss",
            context="CNC/Dark scenes need a clean exit from the fiction, not just a pause.",
        ))

    return items


def build_safe_word_recommendations(questionnaire: SceneQuestionnaire) -> list[SafeWordRecommendation]:
    """Suggest archetype-appropriate safe words and gestures.
    Two-tier (yellow=pause, red=stop) for intense archetypes.
    """
    archetype = questionnaire.archetype
    if archetype in {ArchetypeType.ROMANTIC, ArchetypeType.PLAYFUL}:
        return [SafeWordRecommendation(
            word="pause",
            gesture="raise an open hand",
            useCase="Either of you can call this if anything stops feeling good. The scene halts immediately for a check-in.",
        )]
    if archetype in {ArchetypeType.POWER_EXCHANGE, ArchetypeType.TABOO_LIGHT}:
        return [
            SafeWordRecommendation(
                word="yellow",
                gesture="tap twice on a shoulder or thigh",
                useCase="Slow down or check in without breaking the scene.",
            ),
            SafeWordRecommendation(
                word="red",
                gesture="three rapid taps or drop a held object",
                useCase="Full stop. The scene ends and aftercare begins.",
            ),
        ]
    # CNC / DARK: explicit stop + pause + a non-verbal option since speech is
    # part of the fiction.
    return [
        SafeWordRecommendation(
            word="yellow",
            gesture="tap twice on a shoulder or thigh",
            useCase="Pause without ending the scene. Useful for adjustment or breath.",
        ),
        SafeWordRecommendation(
            word="red",
            gesture="three rapid taps or drop a held object",
            useCase="Full stop. The scene ends immediately and aftercare begins. This word is never in-character.",
        ),
        SafeWordRecommendation(
            word="(reality anchor of your choosing)",
            gesture="open both palms upward",
            useCase="Distinct from 'red' — signals you want the fiction off entirely, not just paused.",
        ),
    ]


def build_aftercare_guide(questionnaire: SceneQuestionnaire) -> list[AftercareSuggestion]:
    archetype = questionnaire.archetype
    base: list[AftercareSuggestion] = [
        AftercareSuggestion(timing="immediate", suggestion="Drop the roles. Use real names, real voice."),
        AftercareSuggestion(timing="immediate", suggestion="Physical reassurance: hold, blanket, water within reach."),
    ]
    if archetype in {ArchetypeType.ROMANTIC, ArchetypeType.PLAYFUL}:
        base.append(AftercareSuggestion(timing="within_hour", suggestion="Light conversation about what felt best — keep it warm and curious."))
        return base

    base.extend([
        AftercareSuggestion(timing="immediate", suggestion="Check for physical needs first: water, food, temperature, restroom."),
        AftercareSuggestion(timing="within_hour", suggestion="Quiet co-presence is enough. Silence is fine; words are optional."),
        AftercareSuggestion(timing="within_hour", suggestion="If either of you feels strange — sad, weepy, jittery — name it without alarm. It's a normal post-scene drop."),
    ])
    if archetype in {ArchetypeType.POWER_EXCHANGE, ArchetypeType.TABOO_LIGHT}:
        base.append(AftercareSuggestion(timing="next_day", suggestion="Briefly check in tomorrow: any lingering thoughts, anything you'd change next time?"))
        return base

    # CNC / DARK
    base.extend([
        AftercareSuggestion(timing="immediate", suggestion="The submissive/receiving partner sets the pace of recovery, not the dominant/giving partner."),
        AftercareSuggestion(timing="next_day", suggestion="Schedule a real conversation tomorrow about how the scene landed emotionally — not just whether it 'worked'."),
        AftercareSuggestion(timing="next_day", suggestion="Watch for delayed drop in the next 24–72 hours. It can show up as low mood, doubt, or detachment. It passes; name it if it appears."),
    ])
    return base


def build_debrief_template(questionnaire: SceneQuestionnaire) -> list[DebriefQuestion]:
    archetype = questionnaire.archetype
    depth = policy_for(archetype)["debriefDepth"]
    pool: list[DebriefQuestion] = [
        DebriefQuestion(question="What landed best for you?", category="emotional"),
        DebriefQuestion(question="Was anything uncomfortable in a way you didn't want?", category="emotional"),
        DebriefQuestion(question="Did the pacing work for you?", category="roleplay"),
        DebriefQuestion(question="Anything you'd change next time?", category="next_time"),
        DebriefQuestion(question="Anything you'd want more of?", category="next_time"),
        DebriefQuestion(question="How does your body feel now compared to before the scene?", category="physical"),
        DebriefQuestion(question="Did it feel like the character lived in the scene, or did it feel like acting?", category="roleplay"),
        DebriefQuestion(question="Was there a moment you almost wanted to stop? What made you keep going?", category="emotional"),
    ]
    return pool[:depth]


def compatibility_score(comparison: dict[str, Any]) -> float:
    matches = len(comparison.get("matches", []))
    blocked = len(comparison.get("blocked", []))
    total = matches + blocked
    if total == 0:
        return 0.0
    return round(matches / total, 3)


# ---------------------------------------------------------------------------
# AI generation (narrative + structured)
# ---------------------------------------------------------------------------


_SCHEMA_INSTRUCTION = """\
You are the Fantasy Creator engine. You produce a JSON object describing a
consensual adult roleplay fantasy for two named participants. Output ONLY
valid JSON — no preface, no explanation, no markdown fences.

The output JSON MUST match this shape exactly:

{
  "title": "string — a short evocative title (no placeholder text)",
  "synopsis": "string — 2-4 sentence summary of the scene",
  "content": "string — 3-6 paragraphs of narrative description of the scene from a neutral storyteller perspective",
  "roles": [
    {
      "personAlias": "Person A or Person B alias as supplied",
      "roleName": "the in-fiction character (e.g., 'The Strict Tutor')",
      "characterDescription": "1-3 sentences about who this character is",
      "guidance": "1-3 sentences advising the player on how to inhabit this role",
      "powerPosition": "dominant | submissive | switch | neutral"
    }
  ],
  "props": [
    { "item": "string", "tier": "required | nice_to_have | advanced", "note": "string", "sensitive": false }
  ],
  "moodTips": [
    { "category": "ambiance | sensory | timing | apparel | digital", "tip": "string" }
  ],
  "scriptPhases": [
    {
      "phaseName": "string (e.g., 'Opening')",
      "phaseType": "opening | rising | peak | aftercare",
      "lines": [
        { "speaker": "PersonAAlias | PersonBAlias | narrator", "lineType": "action | dialogue | direction | safe_word_check", "text": "string", "note": "" }
      ]
    }
  ]
}

Rules:
- Honour the safety principle: "Fantasy interest is not real-world consent." This is a fictional scene between two people who have already agreed to enact it.
- Do not produce graphic anatomical detail. Stay sensual/evocative, not pornographic.
- Use the supplied aliases verbatim for the two participants — do not invent different names.
- Give exactly two role entries, one per participant.
- Provide 3-7 props, 4-7 mood tips, and 3-5 script phases.
- Each script phase needs at least 4 lines.
- If the safety policy requires it, include `safe_word_check` lines at phase transitions with text like "[Pause: agreed safe-words remain in effect]".
- Refuse and return a brief refusal in the synopsis if the request asks for content involving minors or non-consenting third parties — the participants themselves consenting to roleplay does not change this.
"""


def _build_user_prompt(
    prompt_params: dict[str, Any],
    matched_themes: list[dict[str, Any]],
    soft_caution_topics: list[str],
    fade_to_black: bool,
) -> str:
    theme_lines = []
    for theme in matched_themes:
        theme_lines.append(
            f"- {theme.get('label')} (interest: {theme.get('fantasyInterest')}, intensity: {theme.get('intensityPreference')}, role: {theme.get('giverReceiverRole')})"
        )
    theme_block = "\n".join(theme_lines) if theme_lines else "- (no overlapping themes — keep the scene very gentle)"

    soft_block = ""
    if soft_caution_topics:
        soft_block = "Soft-caution topics — present in interest but flagged for negotiation; do not lean on these without a clear off-ramp:\n" + "\n".join(f"- {t}" for t in soft_caution_topics)

    aftercare_directive = (
        "Include an `aftercare` phase at the end of scriptPhases."
        if prompt_params["includeAftercare"]
        else "Do not add an aftercare phase to scriptPhases — that section is omitted by user choice."
    )
    safe_word_directive = (
        f"Embed `safe_word_check` lines at the boundary between every adjacent phase. The agreed pause word is 'yellow' and stop word is 'red'."
        if prompt_params["policy"]["safeWordsInScript"]
        else "Safe-word checks are not required to appear in the script for this archetype."
    )

    fade_directive = (
        "Use fade-to-black for any explicit physical beats — describe the lead-in and the after, not the act."
        if fade_to_black
        else "Sensuality is welcome on-page, but stay evocative rather than anatomical."
    )

    return f"""\
Two participants are planning a real-world roleplay scene together. Generate the
scene structure and script for them. They have already agreed to perform this
fantasy — your job is to give them a usable script and prep guide.

Participants:
- {prompt_params['personAAlias']} (referred to as Person A in the scene)
- {prompt_params['personBAlias']} (referred to as Person B in the scene)

Scene parameters:
- Archetype: {prompt_params['archetypeLabel']} — {prompt_params['archetypeDirective']}
- Setting: {prompt_params['settingLabel']}
- Tone: {prompt_params['toneDirective']}
- Pacing: {prompt_params['pacingDirective']}
- Intensity ceiling: {prompt_params['intensityCap']}
- Fade-to-black: {fade_directive}

Mutually compatible themes from the partners' preference comparison (use these as scene texture):
{theme_block}

{soft_block}

Safety policy:
- Aftercare: {prompt_params['policy']['aftercareTier']}. {aftercare_directive}
- Safe words in script: {prompt_params['policy']['safeWordsInScript']}. {safe_word_directive}
- Consent banner level: {prompt_params['policy']['consentBannerLevel']}.

Now produce the JSON object as specified by the system instructions.
"""


def _coerce_role(raw: Any, alias_a: str, alias_b: str, idx: int) -> FantasyRole:
    if not isinstance(raw, dict):
        raw = {}
    alias = raw.get("personAlias") or (alias_a if idx == 0 else alias_b)
    return FantasyRole(
        personAlias=str(alias),
        roleName=str(raw.get("roleName") or "Character"),
        characterDescription=str(raw.get("characterDescription") or ""),
        guidance=str(raw.get("guidance") or ""),
        powerPosition=raw.get("powerPosition") if raw.get("powerPosition") in {"dominant", "submissive", "switch", "neutral"} else None,
    )


def _coerce_prop(raw: Any) -> FantasyProp | None:
    if not isinstance(raw, dict) or not raw.get("item"):
        return None
    tier = raw.get("tier")
    if tier not in {"required", "nice_to_have", "advanced"}:
        tier = "nice_to_have"
    return FantasyProp(
        item=str(raw["item"]),
        tier=tier,
        note=str(raw.get("note") or ""),
        sensitive=bool(raw.get("sensitive", False)),
    )


def _coerce_mood(raw: Any) -> MoodTip | None:
    if not isinstance(raw, dict) or not raw.get("tip"):
        return None
    cat = raw.get("category")
    if cat not in {"ambiance", "sensory", "timing", "apparel", "digital"}:
        cat = "ambiance"
    return MoodTip(category=cat, tip=str(raw["tip"]))


def _coerce_script_line(raw: Any) -> ScriptLine | None:
    if not isinstance(raw, dict) or not raw.get("text"):
        return None
    line_type = raw.get("lineType")
    if line_type not in {"action", "dialogue", "direction", "safe_word_check"}:
        line_type = "dialogue"
    return ScriptLine(
        speaker=str(raw.get("speaker") or "narrator"),
        lineType=line_type,
        text=str(raw["text"]),
        note=str(raw.get("note") or ""),
    )


def _coerce_script_phase(raw: Any) -> ScriptPhase | None:
    if not isinstance(raw, dict):
        return None
    lines = [ln for ln in (_coerce_script_line(x) for x in (raw.get("lines") or [])) if ln]
    if not lines:
        return None
    phase_type = raw.get("phaseType")
    if phase_type not in {"opening", "rising", "peak", "aftercare"}:
        phase_type = "rising"
    return ScriptPhase(
        phaseName=str(raw.get("phaseName") or "Phase"),
        phaseType=phase_type,
        lines=lines,
    )


def _validate_ai_output(
    raw: dict[str, Any],
    questionnaire: SceneQuestionnaire,
) -> dict[str, Any]:
    """Coerce a possibly-malformed AI dict into the structured shape with safe defaults."""
    alias_a = questionnaire.personAAlias.strip() or "Person A"
    alias_b = questionnaire.personBAlias.strip() or "Person B"

    title = str(raw.get("title") or "").strip() or "Untitled Scene"
    synopsis = str(raw.get("synopsis") or "").strip()
    content = str(raw.get("content") or "").strip()

    roles_raw = raw.get("roles") or []
    if not isinstance(roles_raw, list):
        roles_raw = []
    roles: list[FantasyRole] = []
    for idx, role_raw in enumerate(roles_raw[:2]):
        roles.append(_coerce_role(role_raw, alias_a, alias_b, idx))
    while len(roles) < 2:
        roles.append(_coerce_role({}, alias_a, alias_b, len(roles)))

    props = [p for p in (_coerce_prop(x) for x in (raw.get("props") or [])) if p]
    moods = [m for m in (_coerce_mood(x) for x in (raw.get("moodTips") or [])) if m]
    phases = [ph for ph in (_coerce_script_phase(x) for x in (raw.get("scriptPhases") or [])) if ph]

    return {
        "title": title,
        "synopsis": synopsis,
        "content": content,
        "roles": roles,
        "props": props,
        "moodTips": moods,
        "scriptPhases": phases,
    }


def _fallback_ai_output(
    prompt_params: dict[str, Any],
    matched_themes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Used when the AI call fails — produces a usable shell so the rest of
    the pipeline (rule-based safety, save, export) still works.
    """
    alias_a = prompt_params["personAAlias"]
    alias_b = prompt_params["personBAlias"]
    archetype_label = prompt_params["archetypeLabel"]
    setting = prompt_params["settingLabel"]
    theme_labels = [t.get("label") for t in matched_themes if t.get("label")]
    theme_phrase = ", ".join(theme_labels[:3]) if theme_labels else "shared trust"

    title = f"A {archetype_label} Scene"
    synopsis = (
        f"A {archetype_label.lower()} scene set in {setting}, built around {theme_phrase}. "
        "(Generated as a draft because the AI generation step was unavailable — edit freely.)"
    )
    content = (
        f"This is a placeholder narrative for a {archetype_label.lower()} scene between {alias_a} and {alias_b}.\n\n"
        f"The setting is {setting}. Use {theme_phrase} as the scene's connective tissue.\n\n"
        "Edit this draft into the story you want before playing it out — the rule-based "
        "safety sections (negotiation checklist, safe words, aftercare, debrief) are "
        "already populated and accurate."
    )
    roles = [
        FantasyRole(personAlias=alias_a, roleName="Lead Character", characterDescription="", guidance="", powerPosition=None),
        FantasyRole(personAlias=alias_b, roleName="Counterpart", characterDescription="", guidance="", powerPosition=None),
    ]
    return {
        "title": title,
        "synopsis": synopsis,
        "content": content,
        "roles": roles,
        "props": [],
        "moodTips": [],
        "scriptPhases": [],
    }


def _ensure_safe_word_checks(
    phases: list[ScriptPhase],
    questionnaire: SceneQuestionnaire,
) -> list[ScriptPhase]:
    """For archetypes that require safe-word checks at phase boundaries, make
    sure each transition has one. The AI may have included these already; if
    so, leave them alone.
    """
    if not policy_for(questionnaire.archetype)["safeWordsInScript"]:
        return phases
    if not phases:
        return phases

    out: list[ScriptPhase] = []
    for idx, phase in enumerate(phases):
        out.append(phase)
        if idx == len(phases) - 1:
            continue
        # If the phase already ends with a safe-word check, skip injection.
        already_has = any(line.lineType == "safe_word_check" for line in phase.lines[-2:])
        if already_has:
            continue
        injected = ScriptPhase(
            phaseName="Safe-Word Check",
            phaseType="rising",
            lines=[
                ScriptLine(
                    speaker="narrator",
                    lineType="safe_word_check",
                    text="[Pause briefly. Confirm the agreed safe words remain in effect — 'yellow' to slow, 'red' to stop. Continue when both partners are ready.]",
                    note="",
                )
            ],
        )
        out.append(injected)
    return out


def _matched_themes_for_prompt(comparison: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    matches = comparison.get("matches", [])
    # Sort by a rough "shared interest" rank then by stricter intensity.
    def _rank(m: dict[str, Any]) -> tuple[int, int]:
        return (
            FANTASY_RANK.get(_lookup_enum(m.get("fantasyInterest"), "fantasy"), 0),
            INTENSITY_RANK.get(_lookup_enum(m.get("intensityPreference"), "intensity"), 0),
        )
    return sorted(matches, key=_rank, reverse=True)[:limit]


def _lookup_enum(value: Any, kind: str) -> Any:
    """Best-effort coercion: comparison output uses .value strings; FANTASY_RANK
    is keyed by enum. Try both."""
    if kind == "fantasy":
        from preference_schema import FantasyInterest
        try:
            return FantasyInterest(value)
        except Exception:
            return FantasyInterest.NONE
    if kind == "intensity":
        try:
            return IntensityPreference(value)
        except Exception:
            return IntensityPreference.LIGHT
    return value


def _soft_caution_topics(comparison: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for match in comparison.get("matches", []):
        if match.get("realWorldWillingness") in {"discuss_only", "maybe", "soft_no"}:
            label = match.get("label")
            if label:
                out.append(label)
    return out


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


async def generate_structured_fantasy(
    first: UserPreferenceProfile,
    second: UserPreferenceProfile,
    questionnaire: SceneQuestionnaire,
    *,
    model: str,
    timeout: float = 90.0,
) -> GeneratedFantasy:
    """Build a full structured fantasy by combining rule-based safety output
    with an AI-generated narrative core.
    """
    comparison = compare_profiles(first, second, context=ContextType.PARTNER)
    merged = merge_preferences(first, second, context=ContextType.PARTNER)

    # Derive the merged intensity ceiling from the merged themes — the highest
    # intensity that survived the merger's veto/floor logic. Defaults to MODERATE
    # when there are no surviving themes (the safer default).
    merged_intensity = IntensityPreference.MODERATE
    intensities = []
    for theme in merged.selected_themes:
        try:
            intensities.append(IntensityPreference(theme.get("intensityPreference")))
        except (ValueError, TypeError):
            continue
    if intensities:
        merged_intensity = max(intensities, key=lambda x: INTENSITY_RANK[x])

    prompt_params = map_questionnaire_to_prompt_params(questionnaire, merged_intensity)
    matched_themes = _matched_themes_for_prompt(comparison)
    soft_topics = _soft_caution_topics(comparison)
    fade_to_black = bool(first.globalPreferences.fadeToBlack or second.globalPreferences.fadeToBlack)

    # AI step
    user_prompt = _build_user_prompt(prompt_params, matched_themes, soft_topics, fade_to_black)
    log.info("fantasy_generator: calling model=%s archetype=%s", model, questionnaire.archetype.value)
    ai_dict, err = await complete_json_detail(
        messages=[
            {"role": "system", "content": _SCHEMA_INSTRUCTION},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        timeout=timeout,
        num_predict=2048,
    )
    if err or ai_dict is None:
        log.warning("fantasy_generator: AI call failed (%s); falling back to template", err)
        ai_payload = _fallback_ai_output(prompt_params, matched_themes)
    else:
        ai_payload = _validate_ai_output(ai_dict, questionnaire)

    # Wire up the structured pieces
    script_phases = _ensure_safe_word_checks(ai_payload["scriptPhases"], questionnaire)

    # Build the snapshot from the first profile against matched theme ids — we
    # don't expose the second profile's solo data in the saved fantasy.
    first_items = {item.id: (cat_id, item) for cat_id, item in iter_items(first)}
    selected_pairs = []
    for theme in matched_themes:
        pair = first_items.get(theme.get("id"))
        if pair:
            selected_pairs.append(pair)
    snapshot = build_preference_snapshot(first, selected_pairs, include_reality_bridge=False)

    seed_prompt = (
        f"Roleplay scene for two consenting adults. Archetype: {prompt_params['archetypeLabel']}. "
        f"Setting: {prompt_params['settingLabel']}. Tone: {questionnaire.tone.value}. "
        f"Pacing: {questionnaire.pacing.value}. Intensity ceiling: {prompt_params['intensityCap']}. "
        "Fantasy interest is not real-world consent."
    )

    campaign_seed = CampaignSeed(
        worldConcept=f"{prompt_params['archetypeLabel']} scene set in {prompt_params['settingLabel']}.",
        startingScene=ai_payload["synopsis"][:400] or "Begin at the moment the scene opens.",
        protagonistGuidance="Two consenting adults enacting a pre-negotiated fantasy. Honor each role as written.",
        lorebook={
            "FantasyBoundary": "Fantasy interest is fictional roleplay data and never real-world consent.",
            "Archetype": prompt_params["archetypeLabel"],
            "SafetyPolicy": (
                f"Aftercare={prompt_params['policy']['aftercareTier']}; "
                f"SafeWordChecks={prompt_params['policy']['safeWordsInScript']}; "
                f"ConsentBanner={prompt_params['policy']['consentBannerLevel']}."
            ),
        },
        selectedThemeIds=[t.get("id") for t in matched_themes if t.get("id")],
    )

    now = now_iso()
    fantasy = GeneratedFantasy(
        ownerProfileId=first.profileId,
        ownerUserId=first.userId,
        title=ai_payload["title"],
        createdAt=now,
        updatedAt=now,
        createdFromProfileVersion=first.profileVersion,
        preferenceSnapshot=snapshot,
        sharingMode=SharingMode.OVERLAP_ONLY,
        seedPrompt=seed_prompt,
        synopsis=ai_payload["synopsis"],
        content=ai_payload["content"],
        campaignSeed=campaign_seed,
        secondProfileId=second.profileId,
        archetype=questionnaire.archetype,
        sceneQuestionnaire=questionnaire,
        roles=ai_payload["roles"],
        props=ai_payload["props"],
        moodTips=ai_payload["moodTips"],
        scriptPhases=script_phases,
        aftercareGuide=build_aftercare_guide(questionnaire) if prompt_params["includeAftercare"] else [],
        safeWordRecommendations=build_safe_word_recommendations(questionnaire) if prompt_params["includeSafeWords"] else [],
        negotiationChecklist=build_negotiation_checklist(comparison, questionnaire),
        debriefTemplate=build_debrief_template(questionnaire) if prompt_params["includeDebrief"] else [],
        compatibilityScore=compatibility_score(comparison),
    )
    return fantasy


async def generate_tone_variant(
    base: GeneratedFantasy,
    first: UserPreferenceProfile,
    second: UserPreferenceProfile,
    direction: str,
    *,
    model: str,
    timeout: float = 90.0,
) -> GeneratedFantasy:
    """Generate a lighter or darker tone variant of an existing fantasy.
    `direction` is 'lighter' or 'darker'.
    """
    if base.sceneQuestionnaire is None:
        raise ValueError("Base fantasy has no questionnaire — cannot generate a variant.")

    questionnaire = base.sceneQuestionnaire.model_copy(deep=True)
    if direction == "lighter":
        # Step intensity down one level if possible; soften tone.
        rank = {"intense": IntensityPreference.MODERATE, "moderate": IntensityPreference.LIGHT, "light": IntensityPreference.LIGHT}
        current = (questionnaire.intensityOverride or IntensityPreference.MODERATE).value
        questionnaire.intensityOverride = rank.get(current, IntensityPreference.LIGHT)
    elif direction == "darker":
        rank = {"light": IntensityPreference.MODERATE, "moderate": IntensityPreference.INTENSE, "intense": IntensityPreference.INTENSE}
        current = (questionnaire.intensityOverride or IntensityPreference.MODERATE).value
        questionnaire.intensityOverride = rank.get(current, IntensityPreference.INTENSE)
    else:
        raise ValueError(f"Unknown tone variant direction: {direction!r}")

    variant = await generate_structured_fantasy(first, second, questionnaire, model=model, timeout=timeout)
    variant.toneVariantOf = base.id
    return variant


# Re-export json for the small "we received raw model text" debug path callers
# may want, without forcing them to import json themselves.
__all__ = [
    "generate_structured_fantasy",
    "generate_tone_variant",
    "build_negotiation_checklist",
    "build_safe_word_recommendations",
    "build_aftercare_guide",
    "build_debrief_template",
    "compatibility_score",
    "ARCHETYPE_DESCRIPTIONS",
]
