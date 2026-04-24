"""Schema sanity tests."""

from schema import (
    SCHEMA_VERSION,
    CampaignState,
    Disposition,
    Message,
    NPC,
    Role,
    StateDelta,
)


def test_campaign_state_defaults():
    s = CampaignState(campaign_id="t1")
    assert s.schema_version == SCHEMA_VERSION
    assert s.campaign_id == "t1"
    assert s.player.name == "Unknown"
    assert s.models.gm == "llama3"
    assert s.summaries.short == ""
    assert s.messages == []


def test_message_auto_id():
    a = Message(role=Role.USER, content="x")
    b = Message(role=Role.USER, content="x")
    assert a.id != b.id
    assert a.id.startswith("msg_")
    assert len(a.id) >= 8


def test_disposition_enum_strict():
    npc = NPC(name="X", disposition="Friendly")
    assert npc.disposition == Disposition.FRIENDLY

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        NPC(name="X", disposition="frond")


def test_state_delta_allows_partial():
    d = StateDelta.model_validate({"stats_changes": {"Health": -5}})
    assert d.stats_changes == {"Health": -5}
    assert d.location is None
    assert d.inventory_added == []
    assert d.npc_updates == []


def test_state_delta_ignores_extra_keys():
    d = StateDelta.model_validate({"stats_changes": {}, "junk_field": "ignore me"})
    assert d.stats_changes == {}


def test_round_trip_json():
    s = CampaignState(campaign_id="t2")
    s.messages.append(Message(role=Role.USER, content="hello"))
    dumped = s.model_dump(mode="json")
    restored = CampaignState.model_validate(dumped)
    assert restored.campaign_id == s.campaign_id
    assert len(restored.messages) == 1
    assert restored.messages[0].content == "hello"
