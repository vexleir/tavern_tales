"""
State manager: persistence, concurrency, atomic writes, delta application,
reversal, dynamic stats, suspicious-delta clamping.
"""

from __future__ import annotations

import asyncio

import pytest

import state_manager
from schema import CampaignState, Disposition, NPC, NPCUpdate, StateDelta, StatBound


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(temp_state_dir, new_state):
    s = new_state("camp_a")
    await state_manager.save_state(s)
    loaded = await state_manager.load_state("camp_a")
    assert loaded is not None
    assert loaded.campaign_id == "camp_a"
    assert loaded.player.name == s.player.name


@pytest.mark.asyncio
async def test_load_missing_returns_none(temp_state_dir):
    assert await state_manager.load_state("does_not_exist") is None


@pytest.mark.asyncio
async def test_list_and_delete(temp_state_dir, new_state):
    await state_manager.save_state(new_state("camp_1", player_name="Alice"))
    await state_manager.save_state(new_state("camp_2", player_name="Bob"))

    listed = await state_manager.list_campaigns()
    ids = {c.id for c in listed}
    assert ids == {"camp_1", "camp_2"}

    assert await state_manager.delete_campaign("camp_1") is True
    listed = await state_manager.list_campaigns()
    assert {c.id for c in listed} == {"camp_2"}


@pytest.mark.asyncio
async def test_mutate_state_serializes_concurrent_writes(temp_state_dir, new_state):
    """Two concurrent mutators should apply both; no lost writes."""
    await state_manager.save_state(new_state("camp_c", stats={"Health": 100}))

    async def add_gold(amount):
        async def _m(st: CampaignState) -> CampaignState:
            st.player.stats["Gold"] = st.player.stats.get("Gold", 0) + amount
            await asyncio.sleep(0.01)  # force interleaving
            return st
        await state_manager.mutate_state("camp_c", _m)

    await asyncio.gather(*(add_gold(1) for _ in range(10)))

    final = await state_manager.load_state("camp_c")
    assert final.player.stats.get("Gold") == 10


@pytest.mark.asyncio
async def test_atomic_write_produces_no_partial_file(temp_state_dir, new_state):
    """Directly verify no *.tmp is left behind after save."""
    s = new_state("camp_d")
    await state_manager.save_state(s)
    path = state_manager._path_for("camp_d")
    assert path.exists()
    assert not any(p.suffix == ".tmp" for p in path.parent.iterdir())


@pytest.mark.asyncio
async def test_corrupt_file_renamed_and_load_returns_none(temp_state_dir):
    corrupt_path = temp_state_dir / "states" / "camp_bad.json"
    corrupt_path.write_text("{ not valid json", encoding="utf-8")
    assert await state_manager.load_state("camp_bad") is None
    # Original should be moved aside.
    assert not corrupt_path.exists()
    assert any(p.name.startswith("camp_bad.corrupt-") for p in (temp_state_dir / "states").iterdir())


@pytest.mark.asyncio
async def test_apply_state_delta_roundtrip(new_state):
    s = new_state("camp_e", stats={"Health": 100, "Gold": 50}, inventory=["Torch"])
    delta = StateDelta(
        stats_changes={"Health": -20, "Sanity": 15},
        location="The Dungeon",
        inventory_added=["Key"],
        inventory_removed=["Torch"],
        npc_updates=[
            NPCUpdate(name="Gregor", disposition_change="hostile"),
            NPCUpdate(name="Elena", disposition_change="becomes suspicious", secret_revealed="is a spy"),
        ],
    )
    reversal = state_manager.apply_state_delta(s, delta)

    assert s.player.stats["Health"] == 80
    # New dynamic stat starts at 0 + delta (clamped by its new default bounds).
    assert s.player.stats["Sanity"] == 15
    assert s.player.location == "The Dungeon"
    assert "Key" in s.player.inventory
    assert "Torch" not in s.player.inventory
    assert any(n.name == "Gregor" and n.disposition == Disposition.HOSTILE for n in s.npcs)
    elena = next(n for n in s.npcs if n.name == "Elena")
    assert elena.disposition == Disposition.SUSPICIOUS
    assert "is a spy" in elena.secrets_known

    state_manager.apply_reversal(s, reversal)
    assert s.player.stats["Health"] == 100
    assert s.player.location == "Tavern"  # original
    assert "Torch" in s.player.inventory
    assert "Key" not in s.player.inventory
    # Gregor was created by the delta — reversal removes him.
    assert not any(n.name == "Gregor" for n in s.npcs)
    # Elena existed already — reversal reverts disposition + removes secret.
    elena = next(n for n in s.npcs if n.name == "Elena")
    assert elena.disposition == Disposition.NEUTRAL
    assert "is a spy" not in elena.secrets_known


def test_suspicious_delta_is_halved(new_state):
    s = new_state("camp_f", stats={"Health": 100})
    s.stat_bounds["Health"] = StatBound(min=0, max=9999)
    delta = StateDelta(stats_changes={"Health": 5000})
    state_manager.apply_state_delta(s, delta)
    # current=100, |5000| > max(10, 1000) → halve to 2500; clamp <= 9999.
    assert s.player.stats["Health"] == 2600


def test_disposition_normalizes_prose(new_state):
    s = new_state("camp_g", npcs=[NPC(name="Kara", disposition=Disposition.FRIENDLY)])
    delta = StateDelta(npc_updates=[NPCUpdate(name="Kara", disposition_change="grows more suspicious")])
    state_manager.apply_state_delta(s, delta)
    kara = next(n for n in s.npcs if n.name == "Kara")
    assert kara.disposition == Disposition.SUSPICIOUS


def test_disposition_unknown_kept(new_state):
    s = new_state("camp_h", npcs=[NPC(name="Kara", disposition=Disposition.FRIENDLY)])
    delta = StateDelta(npc_updates=[NPCUpdate(name="Kara", disposition_change="frondly")])
    state_manager.apply_state_delta(s, delta)
    kara = next(n for n in s.npcs if n.name == "Kara")
    assert kara.disposition == Disposition.FRIENDLY


def test_dynamic_stat_registers_default_bounds(new_state):
    s = new_state("camp_i", stats={"Health": 100})
    delta = StateDelta(stats_changes={"Mana": 30})
    state_manager.apply_state_delta(s, delta)
    assert s.player.stats["Mana"] == 30
    assert "Mana" in s.stat_bounds


def test_apply_delta_ignores_zero_and_noninteger(new_state):
    s = new_state("camp_j", stats={"Health": 100, "Gold": 50})
    delta = StateDelta(stats_changes={"Health": 0, "Gold": 5})
    state_manager.apply_state_delta(s, delta)
    assert s.player.stats["Health"] == 100
    assert s.player.stats["Gold"] == 55
