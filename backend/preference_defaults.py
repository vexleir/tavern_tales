"""Default BDSM-aware preference categories.

The checklist is inspired by common BDSM/kink negotiation domains, but the
wording is original to Tavern Tales and stays conceptual, neutral, and
non-graphic. Each item still keeps fantasy interest, text-roleplay willingness,
and real-world willingness separate.
"""

from __future__ import annotations

from copy import deepcopy

from preference_schema import (
    FantasyInterest,
    IntensityPreference,
    PartnerSharePermission,
    PreferenceCategory,
    PreferenceItem,
    RealWorldWillingness,
    TextRoleplayWillingness,
    UserPreferenceProfile,
    now_iso,
)


def _item(item_id: str, label: str, description: str) -> PreferenceItem:
    return PreferenceItem(
        id=item_id,
        label=label,
        description=description,
        fantasyInterest=FantasyInterest.NONE,
        realWorldWillingness=RealWorldWillingness.HARD_NO,
        textRoleplayWillingness=TextRoleplayWillingness.NO,
        intensityPreference=IntensityPreference.LIGHT,
        fantasyOnly=True,
        partnerSharePermission=PartnerSharePermission.PRIVATE,
    )


def default_categories() -> list[PreferenceCategory]:
    return [
        PreferenceCategory(
            id="power_dynamics",
            label="Power Dynamics",
            description="Negotiated authority, service, surrender, leadership, and role exchange. Choose the profile's side for each item separately.",
            items=[
                _item("power_guidance", "Dominance, guidance, or leadership", "A theme where one side gives structure, direction, or calm authority and the other side may receive it."),
                _item("power_submission", "Surrender or being guided", "A theme where one side chooses to yield, follow, or be guided within clear limits."),
                _item("power_switching", "Switching between leading and following", "Characters shift who leads and who follows based on mood, scene, or negotiated context."),
                _item("power_service", "Service-oriented dynamic", "One side offers care, usefulness, tasks, or devotion; choose whether this profile gives, receives, or can do either."),
                _item("power_ownership_symbolic", "Symbolic ownership language", "Ownership, belonging, or possession is used as fictional or negotiated language, with side preference chosen separately."),
                _item("power_protocol", "Protocol and etiquette", "Titles, rituals, manners, or formal scene structure matter to the dynamic; choose this profile's side separately."),
                _item("power_training", "Training or improvement arc", "A scene explores practice, discipline, correction, and growth, with side preference chosen separately."),
                _item("power_trust", "Trust-based vulnerability", "A scene focuses on earned trust, boundaries, and emotional safety."),
            ],
        ),
        PreferenceCategory(
            id="control_themes",
            label="Control Themes",
            description="Rules, restraint, permission, anticipation, and clearly bounded control. Choose whether this profile gives control, receives control, or can do either.",
            items=[
                _item("control_rules", "Giving or following structured rules", "The scene uses negotiated rules or rituals as story texture; choose whether this profile sets them, follows them, or can do either."),
                _item("control_permission", "Permission and approval dynamic", "One side asks, waits, grants, or withholds approval within a negotiated framework."),
                _item("control_restraint_light", "Light restraint themes", "Limited movement or symbolic restraint adds tension without graphic detail; choose this profile's side separately."),
                _item("control_blindfold", "Blindfold or sensory focus", "Reduced information, trust, or heightened awareness shapes the scene; choose whether this profile gives, receives, or can do either."),
                _item("control_suspense", "Suspenseful limitations", "Characters navigate constraints, uncertainty, or delayed choices, with side preference chosen separately."),
                _item("control_choice", "Choice under pressure", "One side presents meaningful choices while boundaries remain respected; choose this profile's side separately."),
                _item("control_confinement_symbolic", "Symbolic confinement", "Locked doors, private rooms, or bounded spaces create narrative pressure without implying real-world consent."),
                _item("control_chastity_symbolic", "Symbolic self-control", "Restraint, patience, or delayed gratification is treated as a story motif, with side preference chosen separately."),
            ],
        ),
        PreferenceCategory(
            id="fantasy_elements",
            label="Fantasy Elements",
            description="Fictional roleplay devices, archetypes, costumes, transformations, and taboo-as-fiction boundaries.",
            items=[
                _item("fantasy_magic_bond", "Magical bonds", "A symbolic connection shapes trust, loyalty, or destiny."),
                _item("fantasy_secret_identity", "Secret identities", "Hidden roles, masks, or aliases create dramatic tension."),
                _item("fantasy_transformation", "Symbolic transformation", "A character changes status, role, or self-understanding."),
                _item("fantasy_captor_captive", "Captor and captive fiction", "A fictional high-control scenario is explored with clear fantasy-only framing."),
                _item("fantasy_authority_roleplay", "Authority roleplay", "A scene uses fictional authority, hierarchy, or rank as dramatic structure."),
                _item("fantasy_student_mentor", "Mentor and student", "Instruction, challenge, praise, and correction drive the relationship arc."),
                _item("fantasy_pet_role_symbolic", "Pet or creature role symbolism", "Nonhuman or pet-like roles are used as playful, symbolic identity play."),
                _item("fantasy_mask_costume", "Masks, costumes, or personas", "Clothing, symbols, or assumed identities help define the scene."),
            ],
        ),
        PreferenceCategory(
            id="social_dynamics",
            label="Social Dynamics",
            description="Partner sharing, group context, visibility, secrecy, rivalry, and negotiated attention. Choose this profile's side where a theme has roles.",
            items=[
                _item("social_partner_sharing", "Partner-sharing themes", "A story explores negotiated attention, trust, and boundaries with others."),
                _item("social_observation", "Being observed or witnessed", "This profile may be the side being seen, supervised, or witnessed in a controlled way."),
                _item("social_observing", "Observing or witnessing others", "This profile may be the side watching, supervising, or witnessing without taking over the scene."),
                _item("social_group_scene", "Small-group scene context", "More than two characters are present, with explicit boundaries and roles."),
                _item("social_rivalry", "Rivalry or competition", "Characters use competition as a source of energy and tension."),
                _item("social_chosen_circle", "Chosen circle", "A trusted group or community shapes the scene context."),
                _item("social_public_adjacent", "Public-adjacent secrecy", "The tension comes from discretion, privacy, or almost-being-seen without explicit exposure."),
                _item("social_after_scene_discussion", "After-scene conversation", "Characters compare feelings, meaning, and boundaries after the fictional scene."),
            ],
        ),
        PreferenceCategory(
            id="emotional_tone",
            label="Emotional Tone",
            description="Praise, fear, tenderness, humiliation-as-fiction, intensity, and aftercare needs.",
            items=[
                _item("tone_tender", "Tender and reassuring", "The scene emphasizes care, patience, and emotional steadiness."),
                _item("tone_praise", "Praise and affirmation", "Encouragement, admiration, or approval is a core reward."),
                _item("tone_strict", "Strict but controlled", "The scene feels firm, exacting, and deliberate without becoming unsafe."),
                _item("tone_mysterious", "Mysterious and charged", "The scene emphasizes secrecy, curiosity, and anticipation."),
                _item("tone_playful", "Playful tension", "The scene uses banter, teasing, or games without crossing limits."),
                _item("tone_humiliation_fiction", "Humiliation as fiction", "Embarrassment, status contrast, or teasing is used only within explicit boundaries."),
                _item("tone_fear_suspense", "Fear or suspense play", "The scene uses fictional danger, uncertainty, or intimidation with safety controls."),
                _item("tone_aftercare_focus", "Aftercare-centered resolution", "The story intentionally includes reassurance, grounding, and emotional repair."),
            ],
        ),
        PreferenceCategory(
            id="interaction_style",
            label="Interaction Style",
            description="How scenes are paced, negotiated, described, interrupted, and resolved.",
            items=[
                _item("style_slow_burn", "Slow burn", "The story develops gradually with room for choice and reflection."),
                _item("style_direct", "Direct scene framing", "The setup gets to the central situation quickly and clearly."),
                _item("style_collaborative", "Collaborative worldbuilding", "The user and narrator shape details together as the scene unfolds."),
                _item("style_checkins", "Frequent check-ins", "The scene includes explicit pauses, confirmation, and boundary reminders."),
                _item("style_safeword_visible", "Safeword or pause signal present", "A clear interruption signal exists in-fiction or in the meta-notes."),
                _item("style_fade_to_black", "Fade-to-black handling", "The scene keeps explicit action offscreen while preserving emotion and story stakes."),
                _item("style_negotiation_scene", "Negotiation-focused scene", "The conversation about limits, interests, and expectations is part of the roleplay."),
                _item("style_debrief", "Debrief and reflection", "The ending highlights what worked, what changed, and what remains fictional."),
            ],
        ),
        PreferenceCategory(
            id="sensation_play",
            label="Sensation Play",
            description="Conceptual preferences for tactile intensity, impact, temperature, texture, and sensory contrast. Choose whether this profile gives, receives, or can do either.",
            items=[
                _item("sensation_light_touch", "Light sensory teasing", "Gentle or delicate sensation creates anticipation and focus; choose this profile's side separately."),
                _item("sensation_impact_symbolic", "Impact as story texture", "Percussive sensation is referenced conceptually without graphic detail; choose this profile's side separately."),
                _item("sensation_temperature", "Temperature contrast", "Warm, cool, or changing sensations are used as atmosphere; choose this profile's side separately."),
                _item("sensation_texture", "Texture focus", "Fabric, leather, rope, gloves, or other materials shape the scene mood; choose this profile's side separately."),
                _item("sensation_sound", "Sound and rhythm", "Voice, commands, counting, or repeated sounds build tension, with side preference chosen separately."),
                _item("sensation_endurance", "Endurance or intensity arc", "The scene explores rising intensity and clear stopping points."),
            ],
        ),
        PreferenceCategory(
            id="symbols_and_gear",
            label="Symbols And Gear",
            description="Non-graphic interest in props, clothing, objects, and symbols that define a roleplay mood.",
            items=[
                _item("gear_collar_symbolic", "Collar or token symbolism", "A collar, charm, ribbon, or token represents belonging or agreement."),
                _item("gear_cuffs_symbolic", "Cuffs or restraint symbols", "Restraint objects appear as visual or narrative symbols."),
                _item("gear_rope_aesthetic", "Rope aesthetic", "Rope, knots, or bindings are used for beauty, trust, or ritualized atmosphere."),
                _item("gear_leather_latex_style", "Leather, latex, or formal style", "Distinct clothing or materials help create character, authority, or mood."),
                _item("gear_tools_unseen", "Tools kept offscreen", "Props may be implied or prepared, while explicit use stays undescribed."),
                _item("gear_private_collection", "Private collection or ritual space", "A room, cabinet, or kit signals preparation, care, and boundaries."),
            ],
        ),
    ]


def merge_default_categories(profile: UserPreferenceProfile) -> UserPreferenceProfile:
    """Add newly introduced default categories/items without overwriting answers."""
    defaults = default_categories()
    existing_categories = {category.id: category for category in profile.categories}
    changed = False

    for default_category in defaults:
        existing = existing_categories.get(default_category.id)
        if existing is None:
            profile.categories.append(deepcopy(default_category))
            changed = True
            continue

        existing_item_ids = {item.id for item in existing.items}
        for default_item in default_category.items:
            if default_item.id not in existing_item_ids:
                existing.items.append(deepcopy(default_item))
                changed = True

        if existing.label != default_category.label:
            existing.label = default_category.label
            changed = True
        if existing.description != default_category.description:
            existing.description = default_category.description
            changed = True

        existing_items = {item.id: item for item in existing.items}
        for default_item in default_category.items:
            existing_item = existing_items.get(default_item.id)
            if existing_item is None:
                continue
            if existing_item.label != default_item.label:
                existing_item.label = default_item.label
                changed = True
            if existing_item.description != default_item.description:
                existing_item.description = default_item.description
                changed = True

    if changed:
        profile.updatedAt = now_iso()
    return profile
