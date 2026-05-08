"""Preference questionnaire catalog based on The Ultimate BDSM Checklist.
New personal profiles are seeded from the activity rows at
https://theultimatebdsmchecklist.com/. The site presents each activity
with the same answer columns (tried, rating, future interest, and how),
which map onto Tavern Tales' existing profile item fields.

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
        id='bondage',
        label='Bondage',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Arm and Leg Sleeves ("Armbinders")'),
            CatalogEntry('Breast Bondage'),
            CatalogEntry('Blindfolds'),
            CatalogEntry('Bondage - Light'),
            CatalogEntry('Bondage - Heavy'),
            CatalogEntry('Bondage - All Day/Multi Day'),
            CatalogEntry('Cages/Cells/Closets (Locked Inside Of)'),
            CatalogEntry('Chains (Bound With)'),
            CatalogEntry('Chastity Device/Belts'),
            CatalogEntry('Collars - Worn In Private'),
            CatalogEntry('Collars - Worn In Public'),
            CatalogEntry('Cuffs - Leather'),
            CatalogEntry('Cuffs - Metal'),
            CatalogEntry('Cuffs - Handcuff Style'),
            CatalogEntry('Ear plugs (Sound Deprivation)'),
            CatalogEntry('Gags - Ball'),
            CatalogEntry('Gags - Bit'),
            CatalogEntry('Gags - Cloth'),
            CatalogEntry('Gags - Inflatable'),
            CatalogEntry('Gags - Phallic'),
            CatalogEntry('Gags - Ring'),
            CatalogEntry('Gags - Tape'),
            CatalogEntry('Harnessing - Leather'),
            CatalogEntry('Harnessing - Rope'),
            CatalogEntry('Hoods (Full Head)'),
            CatalogEntry('Immobilisation'),
            CatalogEntry('Leash'),
            CatalogEntry('Leather Restraints'),
            CatalogEntry('Manacles & Irons'),
            CatalogEntry('Mummification'),
            CatalogEntry('Muzzles'),
            CatalogEntry('Rope Bondage - Simple'),
            CatalogEntry('Rope Bondage - Intricate (Shibari)'),
            CatalogEntry('Spreader Bars'),
            CatalogEntry('Stocks (Head & Hands)'),
            CatalogEntry('Straight Jackets'),
            CatalogEntry('Suspension - Upright'),
            CatalogEntry('Suspension - Horizontal'),
            CatalogEntry('Suspension - Inverted'),
            CatalogEntry('Sleep Sacks'),
        ],
    ),
    CatalogCategory(
        id='bodily_fluids_and_functions',
        label='Bodily Fluids and Functions',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Chamber Pot Use'),
            CatalogEntry('Creampie'),
            CatalogEntry('Cum - In Ass'),
            CatalogEntry('Cum - In Mouth'),
            CatalogEntry('Cum - In Vagina'),
            CatalogEntry('Cum - On Body'),
            CatalogEntry('Cutting - Blood Play'),
            CatalogEntry('Golden showers (Urinate On)'),
            CatalogEntry('Human Toilet'),
            CatalogEntry('Injections (Saline)'),
            CatalogEntry('Milking (Made To Produce Breast Milk)'),
            CatalogEntry('Pearl Necklace (Cum On Chest/Throat)'),
            CatalogEntry('Pearl Shower (Cum On Face)'),
            CatalogEntry('Scat (Brown Showers)'),
            CatalogEntry('Swallowing Semen'),
            CatalogEntry('Swallowing Urine'),
        ],
    ),
    CatalogCategory(
        id='fetishes',
        label='Fetishes',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Boot Worship'),
            CatalogEntry('Cock Worship'),
            CatalogEntry('Corsets'),
            CatalogEntry('Cross Dressing'),
            CatalogEntry('Diapers'),
            CatalogEntry('Foot Worship'),
            CatalogEntry('Gas Masks'),
            CatalogEntry('High Heels (Wearing)'),
            CatalogEntry('High Heels (Worship)'),
            CatalogEntry('Leather (Wearing)'),
            CatalogEntry('Lingerie (Wearing)'),
            CatalogEntry('Pussy Worship'),
            CatalogEntry('Rubber/Latex Clothing (Wearing)'),
            CatalogEntry('Slutty Clothing'),
            CatalogEntry('Spandex Clothing'),
        ],
    ),
    CatalogCategory(
        id='humiliation',
        label='Humiliation',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Forced Dressing'),
            CatalogEntry('Forced Feminization'),
            CatalogEntry('Forced Homosexuality'),
            CatalogEntry('Forced Masturbation'),
            CatalogEntry('Forced Nudity'),
            CatalogEntry('Forced Servitude'),
            CatalogEntry('Humiliation In Private'),
            CatalogEntry('Humiliation In Public'),
            CatalogEntry('Lecturing For Misbehaviors'),
            CatalogEntry('Shaving Head Hair'),
            CatalogEntry('Shaving Or Depilation Of Body Hair'),
            CatalogEntry('Standing In Corner (Punishment)'),
            CatalogEntry('Verbal Humiliation'),
        ],
    ),
    CatalogCategory(
        id='impact_rough_play',
        label='Impact & Rough Play',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Breast Whipping'),
            CatalogEntry('Caning - English'),
            CatalogEntry('Caning - Sensation'),
            CatalogEntry('Face Slapping'),
            CatalogEntry('Punching'),
            CatalogEntry('Pussy Punching'),
            CatalogEntry('Pussy Spanking (Smacking)'),
            CatalogEntry('Pussy Whipping'),
            CatalogEntry('Riding Crops'),
            CatalogEntry('Spanking - Hairbrush'),
            CatalogEntry('Spanking - Hand'),
            CatalogEntry('Spanking - Leather Slappers'),
            CatalogEntry('Spanking - Wooden Paddles'),
            CatalogEntry('Spanking - OTK (Over The Knee)'),
            CatalogEntry('Whipping - Belt'),
            CatalogEntry("Whipping - Cat O' 9 Tails"),
            CatalogEntry('Whipping - Flogger'),
            CatalogEntry('Whipping - Single Tail'),
            CatalogEntry('Wrestling'),
        ],
    ),
    CatalogCategory(
        id='intamacy',
        label='Intamacy',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Hand Holding'),
            CatalogEntry('Hugging'),
            CatalogEntry('Kissing (Body)'),
            CatalogEntry('Kissing (Mouth)'),
            CatalogEntry('Public Affection'),
            CatalogEntry('Romance/Affection'),
            CatalogEntry('Sleepover'),
            CatalogEntry('Spooning'),
            CatalogEntry('Using Real Names'),
        ],
    ),
    CatalogCategory(
        id='non_monogomy',
        label='Non-Monogomy',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Fantasy Gang Rape'),
            CatalogEntry('Group Play - Multiple men "Gang Bang"'),
            CatalogEntry('Group Play - Multiple Women & Men'),
            CatalogEntry('Group Play - Orgy'),
            CatalogEntry('Shared (Given To Another Only Temp)'),
            CatalogEntry('Swapping (With One Other Couple)'),
            CatalogEntry('Swinging (Multiple Couples)'),
        ],
    ),
    CatalogCategory(
        id='marking',
        label='Marking',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Branding'),
            CatalogEntry('Scarification (Cutting, Making Scars)'),
            CatalogEntry('Scratching'),
            CatalogEntry('Tattooing (Inking)'),
        ],
    ),
    CatalogCategory(
        id='role_play',
        label='Role Play',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Abandonment (Fantasy)'),
            CatalogEntry('Age play (Not Pedophilia)'),
            CatalogEntry('Animal Role play'),
            CatalogEntry('Auctioned For Charity'),
            CatalogEntry('Fear Play'),
            CatalogEntry('Free Use'),
            CatalogEntry('Human Puppy-Dog Play'),
            CatalogEntry('Infantilism (Baby Play)'),
            CatalogEntry('Initiation Rites'),
            CatalogEntry('Interrogations'),
            CatalogEntry('Kidnapping'),
            CatalogEntry('Medical Scenes'),
            CatalogEntry('Name Change'),
            CatalogEntry('Pony Play'),
            CatalogEntry('Psych Ward Play'),
            CatalogEntry('Prison Scenes'),
            CatalogEntry('Prostitution Fantasy'),
            CatalogEntry('Religious Scenes'),
            CatalogEntry('Schoolroom Scenes'),
            CatalogEntry('Sleep Play (Somnophilia)'),
            CatalogEntry('Switching Roles (Top/Bottom)'),
            CatalogEntry('Total Power Exchange (TPE)'),
            CatalogEntry('Other Role playing'),
        ],
    ),
    CatalogCategory(
        id='sensation_play_non_impact',
        label='Sensation Play (Non-Impact)',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Abrasion (Scraping, Sanding)'),
            CatalogEntry('Asphyxiation'),
            CatalogEntry('Ball Stretching'),
            CatalogEntry('Biting (Being Bitten)'),
            CatalogEntry('Beating (Hard)'),
            CatalogEntry('Beating (Soft)'),
            CatalogEntry('Breath Control (Choking)'),
            CatalogEntry('Breath Control (Mild Restriction)'),
            CatalogEntry('Clamps - Labia/Clit Area'),
            CatalogEntry('Clothespins'),
            CatalogEntry('Dilation'),
            CatalogEntry('Electricity - Internal (Egg or Probe)'),
            CatalogEntry('Electricity - TENS Unit'),
            CatalogEntry('Electricity - Violet Wand'),
            CatalogEntry('Enemas - For Cleansing'),
            CatalogEntry('Enemas - Retention/Training'),
            CatalogEntry('Finger Claws'),
            CatalogEntry('Fire Cupping'),
            CatalogEntry('Fire Play'),
            CatalogEntry('Hair Pulling'),
            CatalogEntry('Hot Wax - Dripping On Body/Genitals'),
            CatalogEntry('Hot Waxing - Hair Removal'),
            CatalogEntry('Ice Cubes'),
            CatalogEntry('Kicking'),
            CatalogEntry('Knife Play (Blood Drawn)'),
            CatalogEntry('Knife Play (No blood)(Sensation)'),
            CatalogEntry('Needle Play'),
            CatalogEntry('Nipple Clamps'),
            CatalogEntry('Nipple Piercing'),
            CatalogEntry('Nipple Play - Pulls, Tugs, Twists'),
            CatalogEntry('Pain - Mild'),
            CatalogEntry('Pain - Severe'),
            CatalogEntry('Piercing (Permanant)'),
            CatalogEntry('Piercing (Temporary)'),
            CatalogEntry('Punishment Scene'),
            CatalogEntry('Riding The Horse (Crotch Torture)'),
            CatalogEntry('Scratching'),
            CatalogEntry('Sensory Deprivation'),
            CatalogEntry('Sleep Deprivation'),
            CatalogEntry('Strapping (Full Body Beating)'),
            CatalogEntry('Suction Cups'),
            CatalogEntry('Teasing'),
            CatalogEntry('Tickling'),
            CatalogEntry('Vampire Gloves'),
            CatalogEntry('Water Torture (Waterboarding)'),
            CatalogEntry('Wartenburg Pinwheel'),
            CatalogEntry('Zippers - Clothespins'),
            CatalogEntry('Zippers - Clamps'),
            CatalogEntry('Zippers - Needles'),
        ],
    ),
    CatalogCategory(
        id='service_restricted_controlled_behavior',
        label='Service & Restricted/Controlled Behavior',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Bathroom Use Control (Permission)'),
            CatalogEntry('Begging'),
            CatalogEntry('Chauffeuring (Driving)'),
            CatalogEntry('Chores (Domestic Service/Housework)'),
            CatalogEntry('Chosen Clothing For'),
            CatalogEntry('Chosen Food For'),
            CatalogEntry('Contract Slave'),
            CatalogEntry('Daily Diary'),
            CatalogEntry('Exercise - Forced/Required'),
            CatalogEntry('Erotic Dancing'),
            CatalogEntry('Eye Contact Restrictions'),
            CatalogEntry('Following Orders'),
            CatalogEntry('Gor Slave Training (Positions)'),
            CatalogEntry('Harems (Serving With Other Subs)'),
            CatalogEntry('Hypnotism'),
            CatalogEntry('Kneeling'),
            CatalogEntry('Manicures'),
            CatalogEntry('Mantra and Meditation'),
            CatalogEntry('Massage'),
            CatalogEntry('Pedicures & Foot Massages'),
            CatalogEntry('Personality Modification'),
            CatalogEntry('Phone Sex'),
            CatalogEntry('Rituals'),
            CatalogEntry('Serving As A Maid'),
            CatalogEntry('Serving As Furniture'),
            CatalogEntry('Serving As Art'),
            CatalogEntry('Serving Other Doms (Supervised Only)'),
            CatalogEntry('Speech Restrictions (When, What, To Whom)'),
            CatalogEntry('Uniform (Wearing)'),
            CatalogEntry('Wearing Symbolic Jewelry'),
            CatalogEntry('Weight Control'),
        ],
    ),
    CatalogCategory(
        id='sexual_activity_penetration',
        label='Sexual Activity & Penetration',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Anal Beads'),
            CatalogEntry('Anal Play'),
            CatalogEntry('Anal Plugs - Small'),
            CatalogEntry('Anal Plugs - Medium'),
            CatalogEntry('Anal Plugs - Large'),
            CatalogEntry('Anal Plugs - Public, Under Clothes'),
            CatalogEntry('Anal Sex'),
            CatalogEntry('Breast Fucking'),
            CatalogEntry('Catheterization'),
            CatalogEntry('Cunnilingus (Giving Oral To A Woman)'),
            CatalogEntry('Cunnilingus (Receiving Oral)'),
            CatalogEntry('Dildos - Anal'),
            CatalogEntry('Dildos - Oral'),
            CatalogEntry('Dildos - Vaginal'),
            CatalogEntry('Double Penetration'),
            CatalogEntry('Fantasy Rape Play'),
            CatalogEntry('Fellatio (Oral Sex On A Penis)'),
            CatalogEntry('Fisting - Anal'),
            CatalogEntry('Fisting - Vaginal'),
            CatalogEntry('Genital Sex'),
            CatalogEntry('Masturbation'),
            CatalogEntry('Orgasm Control'),
            CatalogEntry('Orgasm Denial'),
            CatalogEntry('Sex Machines'),
            CatalogEntry('Sexual Deprivation'),
            CatalogEntry('Sybians'),
            CatalogEntry('Sounding'),
            CatalogEntry('Speculums'),
            CatalogEntry('Strap-On-Dildos (Sucking On)'),
            CatalogEntry('Strap-On-Dildos (Penetrated By)'),
            CatalogEntry('Strap-On-Dildos (Wearing)'),
            CatalogEntry('Triple Penetration'),
            CatalogEntry('Vibrator - Anal'),
            CatalogEntry('Vibrator - External Genital'),
            CatalogEntry('Vibrator - Internal Genital'),
        ],
    ),
    CatalogCategory(
        id='surrealism',
        label='Surrealism',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Alien'),
            CatalogEntry('Furry'),
            CatalogEntry('Futanari'),
            CatalogEntry('Monster/Beast'),
            CatalogEntry('Tentacles'),
            CatalogEntry('Transformation'),
        ],
    ),
    CatalogCategory(
        id='voyeurism_exhibitionism',
        label='Voyeurism/Exhibitionism',
        description="Activities from The Ultimate BDSM Checklist.",
        items=[
            CatalogEntry('Examinations'),
            CatalogEntry('Exhibitionism (Friends)'),
            CatalogEntry('Exhibitionism (Strangers)'),
            CatalogEntry('Forced Nudity (Private)'),
            CatalogEntry('Forced Nudity (Around Others)'),
            CatalogEntry('Modeling For Erotic Photos'),
            CatalogEntry('Outdoor Scenes'),
            CatalogEntry('Video (Watching Others)'),
            CatalogEntry('Video (Recordings Of You)'),
            CatalogEntry('Voyeurism (Watching Others)'),
            CatalogEntry('Voyeurism (Your Dom W/Others)'),
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
