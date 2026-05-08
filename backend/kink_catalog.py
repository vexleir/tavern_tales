"""Condensed preference questionnaire based on The Ultimate BDSM Checklist.

New personal profiles are seeded from broad questions derived from the activity
rows at https://theultimatebdsmchecklist.com/. Each question intentionally
groups many specific checklist rows into one answerable theme while preserving
the preference signals Tavern Tales needs: interest, context, role/direction,
and notes.

The legacy root `Kinks.csv` is left alone for reference, but this module is
canonical for new profile creation.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class CatalogEntry(NamedTuple):
    label: str
    description: str = ""


class CatalogCategory(NamedTuple):
    id: str
    label: str
    description: str
    items: list[CatalogEntry]


CATEGORIES: list[CatalogCategory] = [
    CatalogCategory(
        id="connection_intimacy",
        label="Connection & Intimacy",
        description="Baseline closeness, romance, and affectionate touch.",
        items=[
            CatalogEntry(
                "Affection & intimacy",
                "Kissing, cuddling, romance, sleepovers, public affection, and using real names.",
            ),
            CatalogEntry(
                "Body worship & focused appreciation",
                "Foot, boot, cock, pussy, or other body-focused worship and praise.",
            ),
        ],
    ),
    CatalogCategory(
        id="restraint_bondage",
        label="Restraint & Bondage",
        description="How much physical restraint, sensory restriction, and immobilization appeals.",
        items=[
            CatalogEntry(
                "Light bondage & restraint",
                "Cuffs, simple rope, leather restraints, collars, spreader bars, and basic immobilization.",
            ),
            CatalogEntry(
                "Heavy bondage & confinement",
                "Strict immobilization, cages, stocks, sleep sacks, mummification, and long restraint scenes.",
            ),
            CatalogEntry(
                "Sensory restriction",
                "Blindfolds, ear plugs, hoods, and sensory deprivation.",
            ),
            CatalogEntry(
                "Gags, muzzles, and speech control",
                "Ball/bit/cloth/ring/tape gags, muzzles, and restrictions on speaking.",
            ),
            CatalogEntry(
                "Leashes, collars, and ownership symbols",
                "Private/public collars, leashes, symbolic jewelry, and visible signs of dynamic.",
            ),
            CatalogEntry(
                "Suspension and advanced rope work",
                "Intricate rope, shibari, upright/horizontal/inverted suspension.",
            ),
            CatalogEntry(
                "Chastity and orgasm control",
                "Chastity devices, orgasm denial, orgasm control, and sexual deprivation.",
            ),
        ],
    ),
    CatalogCategory(
        id="service_control",
        label="Service & Control",
        description="Obedience, structured service, and day-to-day control themes.",
        items=[
            CatalogEntry(
                "Service and obedience",
                "Chores, following orders, kneeling, serving roles, contracts, and ritualized service.",
            ),
            CatalogEntry(
                "Lifestyle control",
                "Chosen clothing/food, bathroom permission, exercise requirements, weight control, and diaries.",
            ),
        ],
    ),
    CatalogCategory(
        id="appearance_fetish",
        label="Appearance & Fetish Wear",
        description="Clothing, presentation, and material-focused turn-ons.",
        items=[
            CatalogEntry(
                "Fetish clothing and materials",
                "Lingerie, corsets, leather, latex/rubber, spandex, high heels, and revealing clothing.",
            ),
            CatalogEntry(
                "Forced transformation or presentation play",
                "Forced dressing, feminization, body-hair shaving, name changes, and presentation control.",
            ),
        ],
    ),
    CatalogCategory(
        id="humiliation_power",
        label="Humiliation & Power",
        description="Humiliation, degradation, and authority-driven dynamics.",
        items=[
            CatalogEntry(
                "Humiliation and degradation",
                "Verbal humiliation, public/private humiliation, forced nudity, lecturing, and corner punishment.",
            ),
            CatalogEntry(
                "Power exchange and authority dynamics",
                "Total power exchange, free use, switching roles, initiation rites, and contract-style dynamics.",
            ),
        ],
    ),
    CatalogCategory(
        id="impact_sensation",
        label="Impact & Sensation",
        description="Physical sensation from gentle teasing through higher-risk edge play.",
        items=[
            CatalogEntry(
                "Impact play",
                "Spanking, paddles, floggers, crops, canes, belts, and whipping.",
            ),
            CatalogEntry(
                "Rough physical play",
                "Wrestling, slapping, punching, kicking, and hard or soft beating.",
            ),
            CatalogEntry(
                "Pain and endurance play",
                "Mild/severe pain, punishment scenes, crotch torture, clamps, zippers, and endurance challenges.",
            ),
            CatalogEntry(
                "Temperature and texture sensation",
                "Wax, ice, abrasion, clothespins, suction cups, pinwheels, vampire gloves, tickling, and teasing.",
            ),
            CatalogEntry(
                "Sharp, piercing, and cutting-adjacent play",
                "Knife play, needle play, temporary/permanent piercing, scarification, and branding.",
            ),
            CatalogEntry(
                "Fire and electrical sensation",
                "Fire play, fire cupping, TENS, violet wand, and electrical toys.",
            ),
            CatalogEntry(
                "Breath and fear-based edge play",
                "Choking, breath restriction, water torture, fear play, and other high-risk edge scenes.",
            ),
        ],
    ),
    CatalogCategory(
        id="sexual_activity",
        label="Sexual Activity",
        description="Sex acts, toys, penetration, and orgasm-focused themes.",
        items=[
            CatalogEntry(
                "Sexual basics and oral sex",
                "Genital sex, oral sex, masturbation, and breast-focused sex acts.",
            ),
            CatalogEntry(
                "Anal play and anal penetration",
                "Anal play, plugs, anal toys, and anal sex.",
            ),
            CatalogEntry(
                "Toys, machines, and penetration aids",
                "Dildos, strap-ons, vibrators, sybians, and sex machines.",
            ),
            CatalogEntry(
                "Advanced penetration and medical-adjacent play",
                "Double/triple penetration, fisting, sounding, speculums, catheterization, and dilation.",
            ),
        ],
    ),
    CatalogCategory(
        id="fluids_mess",
        label="Fluids & Mess",
        description="Fluid, body-function, and messy-play themes.",
        items=[
            CatalogEntry(
                "Semen and ejaculation play",
                "Creampie, cum on body/face/chest, swallowing semen, and semen placement preferences.",
            ),
            CatalogEntry(
                "Urine and bathroom-related play",
                "Golden showers, swallowing urine, chamber pot use, and human toilet themes.",
            ),
            CatalogEntry(
                "Blood, lactation, injections, and scat",
                "Blood play, saline injections, lactation/milking, and scat or other body-function edge limits.",
            ),
        ],
    ),
    CatalogCategory(
        id="roleplay_fantasy",
        label="Roleplay & Fantasy",
        description="Scenario, identity, and fictional frame preferences.",
        items=[
            CatalogEntry(
                "Roleplay scenarios",
                "Schoolroom, prison, medical, religious, interrogation, psych ward, auction, and prostitution fantasy scenes.",
            ),
            CatalogEntry(
                "Age, pet, and identity roleplay",
                "Adult age play, infantilism, puppy/pony/animal play, transformation, and identity-shifting scenes.",
            ),
            CatalogEntry(
                "Capture, coercion, and CNC-style fantasy",
                "Kidnapping, abandonment, sleep play, fantasy rape play, and other consent-negotiated coercion fantasies.",
            ),
            CatalogEntry(
                "Surreal or fantasy creatures",
                "Alien, furry, monster/beast, tentacles, futanari, and transformation fantasy.",
            ),
        ],
    ),
    CatalogCategory(
        id="social_visibility",
        label="Social & Visibility",
        description="Other people, public/private visibility, and recording themes.",
        items=[
            CatalogEntry(
                "Group play and non-monogamy",
                "Group play, orgies, swinging, swapping, sharing, and multiple-partner scenes.",
            ),
            CatalogEntry(
                "Voyeurism, exhibitionism, and recording",
                "Watching or being watched, outdoor scenes, erotic photos, video, and public/private nudity.",
            ),
        ],
    ),
    CatalogCategory(
        id="safety_practical",
        label="Safety & Practical Limits",
        description="Practical information partners need before turning preferences into scenes.",
        items=[
            CatalogEntry(
                "Health, safety, and practical limits",
                "Allergies, medical issues, STI/testing concerns, safe words, must-discuss topics, and absolute boundaries.",
            ),
        ],
    ),
]


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "kink"


def _stable_id(category_id: str, label: str, used: set[str]) -> str:
    base = f"klib_{category_id}_{_slugify(label)}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def categorized_kinks() -> list[dict[str, object]]:
    """Return categories with stable per-item ids."""
    used: set[str] = set()
    out: list[dict[str, object]] = []
    for category in CATEGORIES:
        items_out: list[dict[str, str]] = []
        for entry in category.items:
            items_out.append({
                "id": _stable_id(category.id, entry.label, used),
                "label": entry.label,
                "description": entry.description,
            })
        out.append({
            "id": category.id,
            "label": category.label,
            "description": category.description,
            "items": items_out,
        })
    return out


def flat_kinks() -> list[dict[str, str]]:
    """Flat list of all entries across categories. Used by /api/kink-library."""
    flat: list[dict[str, str]] = []
    for category in categorized_kinks():
        for item in category["items"]:  # type: ignore[index]
            flat.append({
                "id": item["id"],
                "label": item["label"],
                "category": category["id"],  # type: ignore[index]
                "categoryLabel": category["label"],  # type: ignore[index]
                "description": item.get("description", ""),
            })
    return flat
