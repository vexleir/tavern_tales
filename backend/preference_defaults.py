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
    """Replace built-in catalog questions with the current default checklist.

    Existing answers are preserved only when an item is still part of the
    current catalog. Custom preferences live outside categories and are left
    untouched.
    """
    defaults = default_categories()
    default_category_ids = {category.id for category in defaults}
    default_item_ids_by_category = {
        category.id: {item.id for item in category.items}
        for category in defaults
    }
    original_category_count = len(profile.categories)
    profile.categories = [
        category for category in profile.categories
        if category.id in default_category_ids
    ]
    changed = len(profile.categories) != original_category_count

    for category in profile.categories:
        default_item_ids = default_item_ids_by_category.get(category.id, set())
        original_item_count = len(category.items)
        category.items = [
            item for item in category.items
            if item.id in default_item_ids
        ]
        if len(category.items) != original_item_count:
            changed = True

    existing_categories = {category.id: category for category in profile.categories}

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
