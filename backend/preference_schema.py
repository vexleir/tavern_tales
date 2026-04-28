"""Preference profile and saved fantasy schemas.

The models here intentionally separate fantasy interest, text-roleplay
willingness, and real-world willingness. Fantasy interest is never consent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PREFERENCE_SCHEMA_VERSION = "1.0.0"
FANTASY_SCHEMA_VERSION = "1.0.0"


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
    intensityPreference: IntensityPreference = IntensityPreference.LIGHT
    giverReceiverRole: GiverReceiverRole = GiverReceiverRole.BOTH
    context: list[ContextType] = Field(default_factory=lambda: [ContextType.AI])
    fantasyOnly: bool = True
    partnerSharePermission: PartnerSharePermission = PartnerSharePermission.PRIVATE
    commentsPrivate: str = ""
    commentsShareable: str = ""
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)


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
    fantasyOnly: bool = True
    context: list[ContextType] = Field(default_factory=lambda: [ContextType.AI])
    partnerSharePermission: PartnerSharePermission = PartnerSharePermission.PRIVATE
    commentsPrivate: str = ""
    commentsShareable: str = ""
    status: CustomPreferenceStatus = CustomPreferenceStatus.ACTIVE
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)


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


class FantasySummary(BaseModel):
    id: str
    ownerProfileId: str
    title: str
    createdAt: str
    updatedAt: str
    createdFromProfileVersion: int
    sharingMode: SharingMode
    passwordProtected: bool = False
