"""Default conceptual preference categories.

Labels and descriptions stay neutral and non-graphic. Users can edit interest
and willingness values, but the default checklist gives the profile shape.
"""

from __future__ import annotations

from preference_schema import (
    FantasyInterest,
    IntensityPreference,
    PartnerSharePermission,
    PreferenceCategory,
    PreferenceItem,
    RealWorldWillingness,
    TextRoleplayWillingness,
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
            description="Conceptual preferences around leadership, agency, trust, and negotiated roles.",
            items=[
                _item("power_guidance", "Guidance and leadership", "One character offers structure, direction, or calm authority."),
                _item("power_switching", "Changing roles", "Characters shift who leads based on the scene and relationship."),
                _item("power_trust", "Trust-based vulnerability", "A scene focuses on earned trust, boundaries, and emotional safety."),
            ],
        ),
        PreferenceCategory(
            id="control_themes",
            label="Control Themes",
            description="Story structures involving rules, suspense, choices, and clearly stated limits.",
            items=[
                _item("control_rules", "Structured rules", "The scene uses negotiated rules or rituals as story texture."),
                _item("control_suspense", "Suspenseful limitations", "Characters navigate constraints, uncertainty, or delayed choices."),
                _item("control_choice", "Choice under pressure", "A character makes meaningful decisions while boundaries remain respected."),
            ],
        ),
        PreferenceCategory(
            id="fantasy_elements",
            label="Fantasy Elements",
            description="Imaginative story devices that remain fictional unless separately discussed.",
            items=[
                _item("fantasy_magic_bond", "Magical bonds", "A symbolic connection shapes trust, loyalty, or destiny."),
                _item("fantasy_secret_identity", "Secret identities", "Hidden roles, masks, or aliases create dramatic tension."),
                _item("fantasy_transformation", "Symbolic transformation", "A character changes status, role, or self-understanding."),
            ],
        ),
        PreferenceCategory(
            id="social_dynamics",
            label="Social Dynamics",
            description="Relationship structures, audience awareness, partner sharing, and group context at a high level.",
            items=[
                _item("social_partner_sharing", "Partner-sharing themes", "A story explores negotiated attention, trust, and boundaries with others."),
                _item("social_rivalry", "Rivalry or competition", "Characters use competition as a source of energy and tension."),
                _item("social_chosen_circle", "Chosen circle", "A trusted group or community shapes the scene context."),
            ],
        ),
        PreferenceCategory(
            id="emotional_tone",
            label="Emotional Tone",
            description="The desired emotional color of scenes and saved fantasies.",
            items=[
                _item("tone_tender", "Tender and reassuring", "The scene emphasizes care, patience, and emotional steadiness."),
                _item("tone_mysterious", "Mysterious and charged", "The scene emphasizes secrecy, curiosity, and anticipation."),
                _item("tone_playful", "Playful tension", "The scene uses banter, teasing, or games without crossing limits."),
            ],
        ),
        PreferenceCategory(
            id="interaction_style",
            label="Interaction Style",
            description="How the roleplay should move, invite participation, and handle scene boundaries.",
            items=[
                _item("style_slow_burn", "Slow burn", "The story develops gradually with room for choice and reflection."),
                _item("style_direct", "Direct scene framing", "The setup gets to the central situation quickly and clearly."),
                _item("style_collaborative", "Collaborative worldbuilding", "The user and narrator shape details together as the scene unfolds."),
            ],
        ),
    ]
