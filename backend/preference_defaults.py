"""Default preference questionnaire — sourced from the curated kink catalog.

Every new profile is seeded with the categories from `kink_catalog.CATEGORIES`,
in display order (vanilla -> edge). Each item starts at "not at all" (interest
scale = 0) so the questionnaire is opt-in to rate.

When the catalog grows, `merge_default_categories` adds the new categories /
items to existing profiles without touching anything the user already rated.
"""

from __future__ import annotations

from copy import deepcopy

import kink_library
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


def _item(item_id: str, label: str, description: str = "") -> PreferenceItem:
    return PreferenceItem(
        id=item_id,
        label=label,
        description=description,
        fantasyInterest=FantasyInterest.NONE,
        realWorldWillingness=RealWorldWillingness.HARD_NO,
        textRoleplayWillingness=TextRoleplayWillingness.NO,
        intensityPreference=IntensityPreference.MODERATE,
        textFantasy=False,
        realWorldFantasy=False,
        fantasyOnly=True,
        partnerSharePermission=PartnerSharePermission.FULL,
        sourceLibrary="kink_library",
    )


def default_categories() -> list[PreferenceCategory]:
    """Build seed categories from the curated catalog."""
    out: list[PreferenceCategory] = []
    for category in kink_library.list_categories():
        items = [
            _item(str(it["id"]), str(it["label"]), str(it.get("description", "")))
            for it in category["items"]  # type: ignore[index]
        ]
        out.append(
            PreferenceCategory(
                id=str(category["id"]),
                label=str(category["label"]),
                description=str(category["description"]),
                items=items,
            )
        )
    return out


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
