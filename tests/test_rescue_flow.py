from quakebot.scenario import ScenarioConfig
from quakebot.agents import MockAgent
from quakebot.env import QuakeBotEnv


def run_mock_episode() -> QuakeBotEnv:
    env = QuakeBotEnv(config=ScenarioConfig(aftershock_target_room='Basement'))
    agent = MockAgent()
    actions = []
    while not env.done:
        action = agent.act(env.observe())
        actions.append(action.type)
        result = env.step(action)
        assert not result.rejected, result.message
    env.test_action_types = actions  # type: ignore[attr-defined]
    return env


def test_mock_agent_accounts_for_all_survivors_without_pathing_errors():
    env = run_mock_episode()
    assert env.detected_count() >= 3
    assert env.evacuated_count() == 2
    assert env.survivors["survivor_office"].evacuated
    assert env.survivors["survivor_apartment_a"].evacuated
    basement = env.survivors["survivor_basement"]
    assert basement.accounting_status in {"awaiting_specialised_extraction", "handoff_complete"}
    assert basement.directly_assessed
    assert env.invalid_actions == 0
    assert env.rescue_notified
    assert env.report_submitted
    assert all(survivor.accounted_for() for survivor in env.survivors.values())


def test_final_report_includes_survivor_specific_statuses():
    env = run_mock_episode()
    assert env.final_report is not None
    assert "survivor_office" in env.final_report
    assert "survivor_apartment_a" in env.final_report
    assert "survivor_basement" in env.final_report
    assert ("awaiting specialised extraction" in env.final_report or "handoff_complete" in env.final_report)


def test_mock_agent_ends_with_submit_report():
    env = run_mock_episode()
    assert env.test_action_types[-1] == "submit_report"  # type: ignore[attr-defined]


def test_successful_run_has_positive_score():
    env = run_mock_episode()
    assert env.score.total > 0
