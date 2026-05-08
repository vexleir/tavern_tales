"""Scene questionnaire and archetype-driven safety policy.

The questionnaire captures the couple's intended tone (archetype, setting,
pacing) before fantasy generation. This module also encodes the safety
policy: which archetypes require aftercare, where safe-word checks must be
embedded in the script, and how prominently consent framing is displayed.
"""

from __future__ import annotations

from typing import Any

from preference_schema import (
    ArchetypeType,
    IntensityPreference,
    SceneQuestionnaire,
    ScenePacing,
    SceneSetting,
    SceneTone,
)


# Archetype → safety policy. Drives generator and UI.
ARCHETYPE_POLICY: dict[ArchetypeType, dict[str, Any]] = {
    ArchetypeType.ROMANTIC: {
        "aftercareTier": "optional",
        "safeWordsInScript": False,
        "consentBannerLevel": "standard",
        "requiresAcknowledgement": False,
        "minIntensityCap": IntensityPreference.MODERATE,
        "debriefDepth": 4,
    },
    ArchetypeType.PLAYFUL: {
        "aftercareTier": "optional",
        "safeWordsInScript": False,
        "consentBannerLevel": "standard",
        "requiresAcknowledgement": False,
        "minIntensityCap": IntensityPreference.MODERATE,
        "debriefDepth": 4,
    },
    ArchetypeType.POWER_EXCHANGE: {
        "aftercareTier": "recommended",
        "safeWordsInScript": True,
        "consentBannerLevel": "elevated",
        "requiresAcknowledgement": False,
        "minIntensityCap": IntensityPreference.INTENSE,
        "debriefDepth": 6,
    },
    ArchetypeType.TABOO_LIGHT: {
        "aftercareTier": "recommended",
        "safeWordsInScript": True,
        "consentBannerLevel": "elevated",
        "requiresAcknowledgement": False,
        "minIntensityCap": IntensityPreference.INTENSE,
        "debriefDepth": 6,
    },
    ArchetypeType.CNC: {
        "aftercareTier": "required",
        "safeWordsInScript": True,
        "consentBannerLevel": "prominent",
        "requiresAcknowledgement": True,
        "minIntensityCap": IntensityPreference.INTENSE,
        "debriefDepth": 8,
    },
    ArchetypeType.DARK: {
        "aftercareTier": "required",
        "safeWordsInScript": True,
        "consentBannerLevel": "prominent",
        "requiresAcknowledgement": True,
        "minIntensityCap": IntensityPreference.INTENSE,
        "debriefDepth": 8,
    },
}


# Display-friendly archetype descriptions used by the API + UI.
ARCHETYPE_DESCRIPTIONS: dict[ArchetypeType, dict[str, str]] = {
    ArchetypeType.ROMANTIC: {
        "label": "Romantic",
        "summary": "Sensual and intimate. Emotional connection over intensity.",
    },
    ArchetypeType.PLAYFUL: {
        "label": "Playful",
        "summary": "Fun, teasing, light-hearted. Roleplay as flirtation.",
    },
    ArchetypeType.POWER_EXCHANGE: {
        "label": "Power Exchange",
        "summary": "Dominant/submissive dynamic. Authority and surrender as scene texture.",
    },
    ArchetypeType.TABOO_LIGHT: {
        "label": "Taboo (Light)",
        "summary": "Forbidden or secret-feeling scenarios. Mild transgression as fiction.",
    },
    ArchetypeType.CNC: {
        "label": "Consensual Non-Consent",
        "summary": "Resistance played as fiction. Both partners consented in advance to the scene.",
    },
    ArchetypeType.DARK: {
        "label": "Dark",
        "summary": "Psychological intensity, fear-as-play, deeper emotional stakes.",
    },
}


SETTING_DESCRIPTIONS: dict[SceneSetting, str] = {
    SceneSetting.DOMESTIC: "a familiar home setting (kitchen, bedroom, living room)",
    SceneSetting.PROFESSIONAL: "a workplace or authority context (office, classroom, study)",
    SceneSetting.FANTASY: "a fictional or fantastical setting (medieval, supernatural, sci-fi)",
    SceneSetting.OUTDOOR: "an outdoor or semi-public location (cabin, garden, secluded beach)",
    SceneSetting.HOTEL: "a hotel room or weekend getaway",
    SceneSetting.CUSTOM: "a custom setting described by the participants",
}


def setting_label(q: SceneQuestionnaire) -> str:
    if q.setting == SceneSetting.CUSTOM and q.customSetting.strip():
        return q.customSetting.strip()
    return SETTING_DESCRIPTIONS.get(q.setting, q.setting.value)


def policy_for(archetype: ArchetypeType) -> dict[str, Any]:
    return ARCHETYPE_POLICY[archetype]


def cap_intensity(
    requested: IntensityPreference | None,
    archetype_cap: IntensityPreference,
    merged_cap: IntensityPreference,
) -> IntensityPreference:
    """Pick the strictest intensity ceiling among requested/archetype/merged."""
    rank = {IntensityPreference.LIGHT: 0, IntensityPreference.MODERATE: 1, IntensityPreference.INTENSE: 2}
    candidates = [archetype_cap, merged_cap]
    if requested is not None:
        candidates.append(requested)
    return min(candidates, key=lambda x: rank[x])


def map_questionnaire_to_prompt_params(
    q: SceneQuestionnaire,
    merged_intensity: IntensityPreference,
) -> dict[str, Any]:
    """Translate questionnaire answers into AI-prompt-shaped parameters.

    The output is what fantasy_generator passes to the model: tone directives,
    pacing directives, intensity ceiling, archetype-specific safety policy.
    """
    archetype = q.archetype
    policy = policy_for(archetype)
    intensity = cap_intensity(q.intensityOverride, policy["minIntensityCap"], merged_intensity)

    tone_directives = {
        SceneTone.TENDER: "Lean into emotional warmth, vulnerability, and slow attentive moments.",
        SceneTone.PLAYFUL: "Use teasing humor, light banter, and a sense of mutual fun.",
        SceneTone.INTENSE: "Build pressure and stakes; let small details land hard.",
        SceneTone.SERIOUS: "Treat the scene with weight; minimize humor; emphasize gravity.",
    }
    pacing_directives = {
        ScenePacing.SLOW_BURN: "Stretch the build-up. Let tension marinate before any peak.",
        ScenePacing.DIRECT: "Move briskly to the heart of the scene without unnecessary preamble.",
        ScenePacing.ESCALATING: "Step up the intensity in clear stages, each one a noticeable shift.",
    }
    archetype_directives = {
        ArchetypeType.ROMANTIC: "Center connection, eye contact, and tenderness. No dominance dynamics unless explicitly requested.",
        ArchetypeType.PLAYFUL: "Keep things light and fun. Roleplay should feel like a shared game.",
        ArchetypeType.POWER_EXCHANGE: "Make the dom/sub dynamic the spine of the scene. Authority and surrender drive every beat.",
        ArchetypeType.TABOO_LIGHT: "Frame the scene around something forbidden or secret. Keep the transgression psychological, not graphic.",
        ArchetypeType.CNC: "This is a consensual roleplay of resistance. Both characters agreed in advance. Resistance must read as performed, never authentic distress. Embed safe-word checkpoints between phases.",
        ArchetypeType.DARK: "Use psychological intensity and fear-as-play. Both characters agreed in advance. Embed safe-word checkpoints between phases.",
    }

    return {
        "archetype": archetype.value,
        "archetypeLabel": ARCHETYPE_DESCRIPTIONS[archetype]["label"],
        "archetypeDirective": archetype_directives[archetype],
        "toneDirective": tone_directives[q.tone],
        "pacingDirective": pacing_directives[q.pacing],
        "settingLabel": setting_label(q),
        "intensityCap": intensity.value,
        "personAAlias": q.personAAlias.strip() or "Person A",
        "personBAlias": q.personBAlias.strip() or "Person B",
        "policy": {
            "aftercareTier": policy["aftercareTier"],
            "safeWordsInScript": policy["safeWordsInScript"],
            "consentBannerLevel": policy["consentBannerLevel"],
            "debriefDepth": policy["debriefDepth"],
        },
        "includeAftercare": q.includeAftercare or policy["aftercareTier"] == "required",
        "includeSafeWords": q.includeSafeWords or policy["safeWordsInScript"],
        "includeDebrief": q.includeDebrief or policy["debriefDepth"] >= 6,
    }
