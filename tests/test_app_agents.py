from quakebot.agents import MockAgent, OllamaAgent, OpenAIAgent
from quakebot.app import _make_agent, render_floor_map
from quakebot.replay import snapshots_to_dicts, run_episode_recording


def test_streamlit_agent_factory_supports_mock():
    agent = _make_agent({"agent_kind": "mock", "model": "", "host": "", "api_key": ""})
    assert isinstance(agent, MockAgent)


def test_streamlit_agent_factory_supports_ollama_cloud():
    agent = _make_agent(
        {"agent_kind": "ollama-cloud", "model": "gpt-oss:20b", "host": "", "api_key": "test-key"}
    )
    assert isinstance(agent, OllamaAgent)
    assert agent.cloud


def test_streamlit_agent_factory_supports_local_ollama():
    agent = _make_agent(
        {"agent_kind": "ollama-local", "model": "llama3.1", "host": "http://localhost:11434", "api_key": ""}
    )
    assert isinstance(agent, OllamaAgent)
    assert not agent.cloud


def test_streamlit_agent_factory_supports_openai():
    agent = _make_agent(
        {"agent_kind": "openai", "model": "gpt-4.1-mini", "host": "", "api_key": "test-key"}
    )
    assert isinstance(agent, OpenAIAgent)


def test_pixel_floor_map_renders_selected_floor_and_sprites():
    snapshot = snapshots_to_dicts(run_episode_recording(max_steps=1))[-1]
    html = render_floor_map(snapshot, "Ground")
    assert "pixel-map" in html
    assert "Ground" in html
    assert "QuakeBot" in html
    assert "Entrance" in html
