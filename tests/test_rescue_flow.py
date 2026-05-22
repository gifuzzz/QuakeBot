from quakebot.agents import MockAgent
from quakebot.env import QuakeBotEnv


def run_mock_episode() -> QuakeBotEnv:
    env = QuakeBotEnv()
    agent = MockAgent()
    while not env.done:
        result = env.step(agent.act(env.observe()))
        assert not result.rejected, result.message
    return env


def test_mock_agent_evacuates_at_least_two_survivors():
    env = run_mock_episode()
    assert env.detected_count() >= 3
    assert env.evacuated_count() >= 2
    assert env.survivors["survivor_office"].evacuated
    assert env.survivors["survivor_apartment_a"].evacuated
    assert env.rescue_notified
    assert env.report_submitted


def test_final_report_includes_survivor_specific_statuses():
    env = run_mock_episode()
    assert env.final_report is not None
    assert "survivor_office" in env.final_report
    assert "survivor_apartment_a" in env.final_report
    assert "survivor_basement" in env.final_report


def test_successful_run_has_positive_score():
    env = run_mock_episode()
    assert env.score.total > 0
