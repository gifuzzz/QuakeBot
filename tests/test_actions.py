from quakebot.actions import parse_action
from quakebot.prompts import SYSTEM_PROMPT
from quakebot.env import QuakeBotEnv


def test_parse_valid_action_dict():
    action = parse_action({"type": "move", "target": "Lobby"})
    assert action.type == "move"
    assert action.target == "Lobby"


def test_invalid_json_becomes_invalid_action():
    action = parse_action("not json")
    assert action.type == "invalid"
    assert "JSON" in (action.reason or "")


def test_markdown_wrapped_json_is_extracted():
    action = parse_action('```json\n{"type":"move","target":"Lobby"}\n```')
    assert action.type == "move"
    assert action.target == "Lobby"


def test_prompt_mentions_not_repeating_completed_actions():
    assert "Do not repeat an action" in SYSTEM_PROMPT
    assert "recommended_next_actions" in SYSTEM_PROMPT
    assert "required_location" in SYSTEM_PROMPT
    assert "mission_accounting" in SYSTEM_PROMPT
    assert "unaccounted" in SYSTEM_PROMPT


def test_removed_public_actions_are_rejected_not_aliased():
    env = QuakeBotEnv()
    for old_action in ("scan_for_life_signs", "listen_for_survivor", "apply_pressure_bandage", "escort_to_exit"):
        result = env.step({"type": old_action})
        assert not result.ok
        assert result.rejected
        assert "Unsupported action type" in result.message
