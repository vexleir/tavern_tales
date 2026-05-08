"""Preference profile and saved fantasy schemas.

The models here intentionally separate fantasy interest, text-roleplay
willingness, and real-world willingness. Fantasy interest is never consent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

PREFERENCE_SCHEMA_VERSION = "1.1.0"
FANTASY_SCHEMA_VERSION = "1.1.0"


def interest_scale_to_enum(scale: int) -> "FantasyInterest":
    """Map the 0-10 'into it' slider onto the existing 5-level enum used
    by the comparison + merger logic. 0=none, 1-3=low, 4-6=medium (5=curious),
    7-9=high, 10=favorite."""
    if scale <= 0:
        return FantasyInterest.NONE
    if scale <= 3:
        return FantasyInterest.LOW
    if scale <= 6:
        return FantasyInterest.MEDIUM
    if scale <= 9:
        return FantasyInterest.HIGH
    return FantasyInterest.FAVORITE


def enum_to_interest_scale(value: "FantasyInterest") -> int:
    """Reverse mapping for migrating legacy items that only have the enum set."""
    return {
        FantasyInterest.NONE: 0,
        FantasyInterest.LOW: 2,
        FantasyInterest.MEDIUM: 5,
        FantasyInterest.HIGH: 8,
        FantasyInterest.FAVORITE: 10,
    }.get(value, 0)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pref_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class FantasyInterest(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FAVORITE = "favorite"


class RealWorldWillingness(str, Enum):
    HARD_NO = "hard_no"
    SOFT_NO = "soft_no"
    DISCUSS_ONLY = "discuss_only"
    MAYBE = "maybe"
    YES = "yes"


class TextRoleplayWillingness(str, Enum):
    NO = "no"
    MAYBE = "maybe"
    YES = "yes"


class IntensityPreference(str, Enum):
    LIGHT = "light"
    MODERATE = "moderate"
    INTENSE = "intense"


class GiverReceiverRole(str, Enum):
    GIVER = "giver"
    RECEIVER = "receiver"
    BOTH = "both"


class ContextType(str, Enum):
    AI = "ai"
    PARTNER = "partner"
    MULTIPLAYER = "multiplayer"


class PartnerSharePermission(str, Enum):
    PRIVATE = "private"
    OVERLAP_ONLY = "overlap_only"
    SUMMARY = "summary"
    FULL = "full"


class ConsentStyle(str, Enum):
    EXPLICIT = "explicit"
    IMPLIED = "implied"
    NEGOTIATED = "negotiated"


class PreferredPOV(str, Enum):
    FIRST = "first"
    THIRD = "third"


class RolePreference(str, Enum):
    DOMINANT = "dominant"
    SUBMISSIVE = "submissive"
    SWITCH = "switch"
    NONE = "none"


class CustomResponseType(str, Enum):
    SCALE = "scale"
    YES_NO = "yes_no"
    MULTI_SELECT = "multi_select"
    TEXT = "text"


class CustomPreferenceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class RealityBridgeIntent(str, Enum):
    DISCUSSION_ONLY = "discussion_only"
    MAYBE_TRY = "maybe_try"
    WANT_TO_TRY = "want_to_try"


class RealityBridgeComfort(str, Enum):
    CURIOUS = "curious"
    CAUTIOUS = "cautious"
    INTERESTED = "interested"
    ENTHUSIASTIC = "enthusiastic"


class SharingMode(str, Enum):
    PRIVATE = "private"
    SUMMARY_ONLY = "summary_only"
    OVERLAP_ONLY = "overlap_only"
    FULL_SCENE = "full_scene"
    FULL_SCENE_WITH_NOTES = "full_scene_with_notes"


class ProfileStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class GlobalPreferences(BaseModel):
    consentStyle: ConsentStyle = ConsentStyle.EXPLICIT
    fadeToBlack: bool = True
    preferredPOV: PreferredPOV = PreferredPOV.THIRD
    rolePreference: RolePreference = RolePreference.NONE
    aftercarePreference: str = ""
    gender: str = ""
    orientation: str = ""
    relationshipStyle: str = ""
    ageAffirmedAt: str | None = None


class PreferenceItem(BaseModel):
    id: str
    label: str
    description: str = ""
    fantasyInterest: FantasyInterest = FantasyInterest.NONE
    realWorldWillingness: RealWorldWillingness = RealWorldWillingness.HARD_NO
    textRoleplayWillingness: TextRoleplayWillingness = TextRoleplayWillingness.NO
    intensityPreference: IntensityPreference = IntensityPreference.MODERATE
    giverReceiverRole: GiverReceiverRole = GiverReceiverRole.BOTH
    context: list[ContextType] = Field(default_factory=lambda: [ContextType.AI])
    # Simplified UI flags. textFantasy + realWorldFantasy together capture what
    # `fantasyOnly` / `textRoleplayWillingness` / `realWorldWillingness` used
    # to express via separate dropdowns. The validator below keeps the legacy
    # enums in sync so the comparison and merger pipelines still work.
    textFantasy: bool = False
    realWorldFantasy: bool = False
    fantasyOnly: bool = True
    partnerSharePermission: PartnerSharePermission = PartnerSharePermission.FULL
    commentsPrivate: str = ""
    commentsShareable: str = ""
    # 0-10 "into it" scale. 0=not at all, 5=curious, 10=completely into it.
    interestScale: int = Field(default=0, ge=0, le=10)
    interestedInLearning: bool = False
    revisitLater: bool = False  # Legacy field, kept for back-compat; UI removed.
    sourceLibrary: str = ""
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _sync_legacy_fields(self) -> "PreferenceItem":
        # interestScale <-> fantasyInterest: scale is the new source of truth,
        # but backfill from the enum if only the enum is set (legacy data).
        if self.interestScale == 0 and self.fantasyInterest != FantasyInterest.NONE:
            object.__setattr__(self, "interestScale", enum_to_interest_scale(self.fantasyInterest))
        else:
            object.__setattr__(self, "fantasyInterest", interest_scale_to_enum(self.interestScale))

        # textFantasy <-> textRoleplayWillingness:
        # checkbox=True forces enum=YES; checkbox=False with enum=YES migrates
        # checkbox to True; intermediate enum states (NO/MAYBE) are preserved.
        if self.textFantasy:
            object.__setattr__(self, "textRoleplayWillingness", TextRoleplayWillingness.YES)
        elif self.textRoleplayWillingness == TextRoleplayWillingness.YES:
            object.__setattr__(self, "textFantasy", True)

        # realWorldFantasy <-> realWorldWillingness:
        # same migration approach. SOFT_NO / DISCUSS_ONLY / MAYBE on the legacy
        # enum are preserved (the simplified checkbox is binary, but tests and
        # legacy data may carry the in-between values).
        if self.realWorldFantasy:
            object.__setattr__(self, "realWorldWillingness", RealWorldWillingness.YES)
        elif self.realWorldWillingness == RealWorldWillingness.YES:
            object.__setattr__(self, "realWorldFantasy", True)

        object.__setattr__(self, "fantasyOnly", bool(self.textFantasy and not self.realWorldFantasy))
        return self


class PreferenceCategory(BaseModel):
    id: str
    label: str
    description: str = ""
    items: list[PreferenceItem] = Field(default_factory=list)


class CustomPreference(BaseModel):
    id: str = Field(default_factory=lambda: pref_id("custom"))
    createdBy: str = ""
    label: str
    description: str = ""
    responseType: CustomResponseType = CustomResponseType.TEXT
    options: list[str] = Field(default_factory=list)
    response: Any = None
    fantasyInterest: FantasyInterest = FantasyInterest.NONE
    realWorldWillingness: RealWorldWillingness = RealWorldWillingness.HARD_NO
    textRoleplayWillingness: TextRoleplayWillingness = TextRoleplayWillingness.NO
    giverReceiverRole: GiverReceiverRole = GiverReceiverRole.BOTH
    textFantasy: bool = False
    realWorldFantasy: bool = False
    fantasyOnly: bool = True
    context: list[ContextType] = Field(default_factory=lambda: [ContextType.AI])
    partnerSharePermission: PartnerSharePermission = PartnerSharePermission.FULL
    commentsPrivate: str = ""
    commentsShareable: str = ""
    interestScale: int = Field(default=0, ge=0, le=10)
    interestedInLearning: bool = False
    revisitLater: bool = False
    sourceLibrary: str = ""
    status: CustomPreferenceStatus = CustomPreferenceStatus.ACTIVE
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _sync_legacy_fields(self) -> "CustomPreference":
        if self.interestScale == 0 and self.fantasyInterest != FantasyInterest.NONE:
            object.__setattr__(self, "interestScale", enum_to_interest_scale(self.fantasyInterest))
        else:
            object.__setattr__(self, "fantasyInterest", interest_scale_to_enum(self.interestScale))
        if self.textFantasy:
            object.__setattr__(self, "textRoleplayWillingness", TextRoleplayWillingness.YES)
        elif self.textRoleplayWillingness == TextRoleplayWillingness.YES:
            object.__setattr__(self, "textFantasy", True)
        if self.realWorldFantasy:
            object.__setattr__(self, "realWorldWillingness", RealWorldWillingness.YES)
        elif self.realWorldWillingness == RealWorldWillingness.YES:
            object.__setattr__(self, "realWorldFantasy", True)
        object.__setattr__(self, "fantasyOnly", bool(self.textFantasy and not self.realWorldFantasy))
        return self


class RealityBridge(BaseModel):
    enabled: bool = False
    intent: RealityBridgeIntent = RealityBridgeIntent.DISCUSSION_ONLY
    comfortLevel: RealityBridgeComfort = RealityBridgeComfort.CURIOUS
    nonNegotiables: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    shareWithPartner: bool = False


class UserPreferenceProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profileId: str = Field(default_factory=lambda: pref_id("profile"))
    userId: str = "local_default"
    displayName: str = "Default Profile"
    profileVersion: int = 1
    schemaVersion: str = PREFERENCE_SCHEMA_VERSION
    status: ProfileStatus = ProfileStatus.ACTIVE
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)
    lastReviewedAt: str = Field(default_factory=now_iso)
    onboardingCompletedAt: str | None = None
    globalPreferences: GlobalPreferences = Field(default_factory=GlobalPreferences)
    categories: list[PreferenceCategory] = Field(default_factory=list)
    customPreferences: list[CustomPreference] = Field(default_factory=list)
    realityBridge: RealityBridge = Field(default_factory=RealityBridge)


class PreferenceProfileSummary(BaseModel):
    profileId: str
    userId: str
    displayName: str
    profileVersion: int
    schemaVersion: str
    status: ProfileStatus
    updatedAt: str
    onboardingCompleted: bool = False


class PreferenceSnapshot(BaseModel):
    profileId: str
    profileVersion: int
    displayName: str = ""
    selectedThemes: list[dict[str, Any]] = Field(default_factory=list)
    excludedThemeIds: list[str] = Field(default_factory=list)
    fantasyOnlyThemeIds: list[str] = Field(default_factory=list)
    realWorldHardNoThemeIds: list[str] = Field(default_factory=list)
    globalContext: dict[str, Any] = Field(default_factory=dict)
    realityBridgeIncluded: bool = False


class CampaignSeed(BaseModel):
    worldConcept: str = ""
    startingScene: str = ""
    protagonistGuidance: str = ""
    lorebook: dict[str, str] = Field(default_factory=dict)
    selectedThemeIds: list[str] = Field(default_factory=list)


class PasswordProtection(BaseModel):
    enabled: bool = False
    protectedAt: str | None = None
    hint: str = ""


class GeneratedFantasy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: pref_id("fantasy"))
    ownerProfileId: str
    ownerUserId: str = "local_default"
    schemaVersion: str = FANTASY_SCHEMA_VERSION
    title: str
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)
    createdFromProfileVersion: int
    preferenceSnapshot: PreferenceSnapshot
    sharingMode: SharingMode = SharingMode.PRIVATE
    seedPrompt: str = ""
    synopsis: str = ""
    content: str = ""
    campaignSeed: CampaignSeed = Field(default_factory=CampaignSeed)
    realityBridgeNotes: str = ""
    passwordProtection: PasswordProtection = Field(default_factory=PasswordProtection)
    protectedContent: dict[str, Any] | None = None

    # Fantasy Creator structured fields. All optional; older fantasies validate
    # against this schema with empty defaults. Populated by fantasy_generator.
    secondProfileId: str | None = None
    archetype: ArchetypeType | None = None
    sceneQuestionnaire: SceneQuestionnaire | None = None
    roles: list[FantasyRole] = Field(default_factory=list)
    props: list[FantasyProp] = Field(default_factory=list)
    moodTips: list[MoodTip] = Field(default_factory=list)
    scriptPhases: list[ScriptPhase] = Field(default_factory=list)
    aftercareGuide: list[AftercareSuggestion] = Field(default_factory=list)
    safeWordRecommendations: list[SafeWordRecommendation] = Field(default_factory=list)
    negotiationChecklist: list[NegotiationItem] = Field(default_factory=list)
    debriefTemplate: list[DebriefQuestion] = Field(default_factory=list)
    compatibilityScore: float | None = None
    toneVariantIds: list[str] = Field(default_factory=list)
    toneVariantOf: str | None = None


class FantasySummary(BaseModel):
    id: str
    ownerProfileId: str
    title: str
    createdAt: str
    updatedAt: str
    createdFromProfileVersion: int
    sharingMode: SharingMode
    passwordProtected: bool = False


# ---------------------------------------------------------------------------
# Fantasy Creator — structured roleplay fantasy models
# ---------------------------------------------------------------------------


class ArchetypeType(str, Enum):
    ROMANTIC = "romantic"
    PLAYFUL = "playful"
    POWER_EXCHANGE = "power_exchange"
    TABOO_LIGHT = "taboo_light"
    CNC = "cnc"
    DARK = "dark"


class SceneSetting(str, Enum):
    DOMESTIC = "domestic"
    PROFESSIONAL = "professional"
    FANTASY = "fantasy"
    OUTDOOR = "outdoor"
    HOTEL = "hotel"
    CUSTOM = "custom"


class SceneTone(str, Enum):
    TENDER = "tender"
    PLAYFUL = "playful"
    INTENSE = "intense"
    SERIOUS = "serious"


class ScenePacing(str, Enum):
    SLOW_BURN = "slow_burn"
    DIRECT = "direct"
    ESCALATING = "escalating"


class SceneQuestionnaire(BaseModel):
    archetype: ArchetypeType
    setting: SceneSetting = SceneSetting.DOMESTIC
    customSetting: str = ""
    tone: SceneTone = SceneTone.PLAYFUL
    pacing: ScenePacing = ScenePacing.SLOW_BURN
    intensityOverride: IntensityPreference | None = None
    includeAftercare: bool = True
    includeSafeWords: bool = True
    includeDebrief: bool = True
    personAAlias: str = "Person A"
    personBAlias: str = "Person B"
    cncAcknowledged: bool = False


class FantasyRole(BaseModel):
    personAlias: str
    roleName: str
    characterDescription: str = ""
    guidance: str = ""
    powerPosition: Literal["dominant", "submissive", "switch", "neutral"] | None = None


class FantasyProp(BaseModel):
    item: str
    tier: Literal["required", "nice_to_have", "advanced"] = "nice_to_have"
    note: str = ""
    sensitive: bool = False


class MoodTip(BaseModel):
    category: Literal["ambiance", "sensory", "timing", "apparel", "digital"] = "ambiance"
    tip: str


class ScriptLine(BaseModel):
    speaker: str = "narrator"
    lineType: Literal["action", "dialogue", "direction", "safe_word_check"] = "dialogue"
    text: str
    note: str = ""


class ScriptPhase(BaseModel):
    phaseName: str
    phaseType: Literal["opening", "rising", "peak", "aftercare"] = "rising"
    lines: list[ScriptLine] = Field(default_factory=list)


class AftercareSuggestion(BaseModel):
    timing: Literal["immediate", "within_hour", "next_day"] = "immediate"
    suggestion: str


class NegotiationItem(BaseModel):
    topic: str
    question: str
    priority: Literal["must_discuss", "recommended", "optional"] = "recommended"
    context: str = ""


class SafeWordRecommendation(BaseModel):
    word: str
    gesture: str = ""
    useCase: str = ""


class DebriefQuestion(BaseModel):
    question: str
    category: Literal["emotional", "physical", "roleplay", "next_time"] = "emotional"
