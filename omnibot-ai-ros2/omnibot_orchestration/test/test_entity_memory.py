import os

import pytest

from omnibot_orchestration.memory.entity_memory import EntityMemory


@pytest.fixture
def mem(tmp_path):
    return EntityMemory(str(tmp_path / "entity_memory.json"))


def test_remember_and_recall(mem):
    mem.remember_object("red_cup", "kitchen", "A red ceramic cup")
    result = mem.recall_object("red_cup")
    assert result is not None
    assert result["last_seen_location"] == "kitchen"
    assert result["description"] == "A red ceramic cup"


def test_recall_unknown_returns_none(mem):
    assert mem.recall_object("nonexistent_object") is None


def test_get_objects_at_location(mem):
    mem.remember_object("blue_bottle", "workspace", "")
    mem.remember_object("scissors", "workspace", "")
    mem.remember_object("coffee_maker", "kitchen", "")
    at_workspace = mem.get_objects_at_location("workspace")
    assert "blue_bottle" in at_workspace
    assert "scissors" in at_workspace
    assert "coffee_maker" not in at_workspace


def test_get_summary_empty(mem):
    summary = mem.get_summary()
    assert "No objects" in summary


def test_get_summary_with_objects(mem):
    mem.remember_object("mug", "kitchen", "A blue mug")
    summary = mem.get_summary()
    assert "mug" in summary
    assert "kitchen" in summary


def test_persistence(tmp_path):
    path = str(tmp_path / "mem.json")
    m1 = EntityMemory(path)
    m1.remember_object("bottle", "hallway", "Green bottle")

    m2 = EntityMemory(path)
    result = m2.recall_object("bottle")
    assert result is not None
    assert result["last_seen_location"] == "hallway"


def test_atomic_write_creates_no_tmp_on_success(tmp_path):
    path = str(tmp_path / "mem.json")
    mem = EntityMemory(path)
    mem.remember_object("item", "home", "")
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")


def test_clear(mem):
    mem.remember_object("cup", "kitchen", "")
    mem.clear()
    assert mem.recall_object("cup") is None
    assert mem.get_summary() == "No objects remembered yet."


def test_duplicate_object_not_duplicated_in_location(mem):
    mem.remember_object("cup", "kitchen", "first time")
    mem.remember_object("cup", "kitchen", "second time")
    objects = mem.get_objects_at_location("kitchen")
    assert objects.count("cup") == 1
