"""Runnable QuakeBot demo episode."""

from __future__ import annotations

import argparse
import json

from .agents import MockAgent, OllamaAgent, OpenAIAgent, RecommendedActionAgent
from .actions import parse_action
from .env import QuakeBotEnv
from .renderer import format_step, format_transcript
from .replay import _snapshot, snapshots_to_dicts
from .scenario import ScenarioConfig
from .scenario_builder import FloorSpec, RoomSpec, ScenarioSpec, SurvivorSpec


def run_episode(
    *,
    agent_kind: str = "mock",
    ollama_model: str | None = None,
    wait_for_enter: bool = False,
    approximate: bool = False,
    random_events: bool = False,
    seed: int = 7,
    scenario: str | None = None,
    save: str | None = None,
) -> QuakeBotEnv:
    config = _scenario_config(approximate, random_events=random_events, seed=seed, scenario=scenario)
    layout = _generated_small_layout() if scenario == "generated_small" else None
    if scenario == "severe_risk_bleeding_survivor":
        layout = _severe_risk_bleeding_survivor_layout()
    env = QuakeBotEnv(config=config, layout=layout)
    if scenario in {"generated_small", "severe_risk_bleeding_survivor"} and agent_kind == "mock":
        agent = RecommendedActionAgent() if scenario == "generated_small" else SevereRiskDemoAgent()
    elif agent_kind == "openai":
        agent = OpenAIAgent()
    elif agent_kind == "ollama":
        agent = OllamaAgent(model=ollama_model)
    elif agent_kind == "ollama-cloud":
        agent = OllamaAgent(model=ollama_model, cloud=True)
    else:
        agent = MockAgent(approximate=approximate)

    if isinstance(agent, OpenAIAgent) and not agent.available:
        print("OPENAI_API_KEY is not set; falling back to MockAgent.")
        agent = MockAgent(approximate=approximate)
    if isinstance(agent, OllamaAgent) and not agent.available:
        if agent.cloud:
            print("Ollama Cloud is not available. Set OLLAMA_API_KEY; falling back to MockAgent.")
        else:
            print("Ollama is not reachable at OLLAMA_HOST; falling back to MockAgent.")
        agent = MockAgent(approximate=approximate)

    transcript: list[str] = []
    snapshots = [_snapshot(env, None, None)]
    while not env.done:
        observation = env.observe()
        if wait_for_enter:
            input(f"Press Enter for step {env.step_count + 1}...")
        action = agent.act(observation)
        result = env.step(action)
        snapshots.append(_snapshot(env, action, result, transcript_observation=observation))
        entry = format_step(env.step_count, observation, action, result)
        transcript.append(entry)
        print(entry)
        print()

    print(format_transcript(transcript, env.final_report, env.score.total))
    
    if save:
        with open(save, "w") as f:
            json.dump(snapshots_to_dicts(snapshots), f, indent=2)

    return env


def _scenario_config(approximate: bool, *, random_events: bool = False, seed: int = 7, scenario: str | None = None) -> ScenarioConfig:
    if scenario == "hidden_survivors_exact":
        return ScenarioConfig(
            survivor_count_mode="exact",
            survivor_count=3,
            survivor_location_mode="unknown",
            random_events_enabled=random_events,
            seed=seed,
            max_steps=140 if random_events else 100,
        )
    if scenario == "hidden_survivors_approximate":
        return ScenarioConfig(
            survivor_count_mode="approximate",
            survivor_count=4,
            survivor_count_min=2,
            survivor_count_max=5,
            survivor_location_mode="unknown",
            random_events_enabled=random_events,
            seed=seed,
            max_steps=160,
        )
    if scenario == "generated_small":
        return ScenarioConfig(
            survivor_count_mode="approximate",
            survivor_count=1,
            survivor_count_min=1,
            survivor_count_max=2,
            survivor_location_mode="unknown",
            random_events_enabled=random_events,
            seed=seed,
            max_steps=80,
        )
    if scenario == "severe_risk_bleeding_survivor":
        return ScenarioConfig(
            survivor_count_mode="exact",
            survivor_count=1,
            survivor_location_mode="unknown",
            random_events_enabled=random_events,
            seed=seed,
            max_steps=110,
        )
    if not approximate:
        return ScenarioConfig(random_events_enabled=random_events, seed=seed, max_steps=140 if random_events else 100)
    return ScenarioConfig(
        survivor_count_mode="approximate",
        survivor_count=4,
        survivor_count_min=3,
        survivor_count_max=5,
        random_events_enabled=random_events,
        seed=seed,
        max_steps=160,
    )


def _generated_small_layout():
    entrance = RoomSpec("Entrance")
    hallway = RoomSpec(
        "Hallway",
        conditions={"structural_risk": "medium", "smoke": "light"},
        objects=["rubble"],
        sounds=["muffled tapping beyond a blocked workshop door"],
        vibration_cues=["weak vibration near the workshop doorway"],
        survivor_cues=["voice beyond obstruction"],
    )
    workshop = RoomSpec(
        "Workshop",
        conditions={"structural_risk": "medium"},
        blocked_by={"type": "rubble", "status": "blocking", "required_location": "Hallway"},
    )
    utility = RoomSpec("Utility_Room", conditions={"structural_risk": "severe", "electrical_hazard": True})
    entrance.connect(hallway)
    hallway.connect(workshop)
    hallway.connect(utility)

    ground = FloorSpec("ground", "Ground Floor", [entrance, hallway, workshop, utility])
    survivor = SurvivorSpec(
        id="survivor_workshop",
        name="Maya",
        location=workshop,
        trapped=True,
        reachable=False,
        breathing_status="fast",
        pulse_status="rapid",
        bleeding="minor",
        pain_level=5,
        can_walk=False,
        suspected_injuries=["leg pinned by furniture"],
        priority="high",
    )
    return ScenarioSpec(
        id="generated_small",
        name="Generated Small Rescue Scenario",
        floors=[ground],
        survivors=[survivor],
    ).compile()


def _severe_risk_bleeding_survivor_layout():
    entrance = RoomSpec("Entrance")
    hallway = RoomSpec("Hallway", conditions={"structural_risk": "medium"})
    board_room = RoomSpec(
        "Board Room",
        conditions={"structural_risk": "severe"},
        sounds=["muffled tapping from behind a warped door"],
        vibration_cues=["weak vibration beyond the board room wall"],
        survivor_cues=["life signs behind the door"],
    )
    entrance.connect(hallway)
    hallway.connect(board_room)

    ground = FloorSpec("ground", "Ground Floor", [entrance, hallway, board_room])
    survivor = SurvivorSpec(
        id="survivor_pari",
        name="Pari",
        location=board_room,
        trapped=True,
        reachable=False,
        conscious=True,
        responsive=True,
        breathing_status="laboured",
        pulse_status="weak",
        bleeding="severe",
        pain_level=8,
        can_walk=False,
        suspected_injuries=["crush injury"],
        priority="critical",
    )
    return ScenarioSpec(
        id="severe_risk_bleeding_survivor",
        name="Severe Risk Bleeding Survivor",
        floors=[ground],
        survivors=[survivor],
    ).compile()


class SevereRiskDemoAgent:
    """Bootstrap agent for the severe-risk demo scenario.

    It takes a fixed safe route to the doorway, performs the life-sign scan,
    and then follows the normal recommendation loop.
    """

    def __init__(self) -> None:
        self.bootstrap_plan = [
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Hallway"},
            {"type": "sense_area", "mode": "life_signs", "target": "Board Room"},
            {"type": "move", "target": "Board Room"},
            {"type": "reassure_survivor", "target": "survivor_pari", "message": "I have you in sight. Stay with me."},
            {"type": "ask_medical_question", "target": "survivor_pari", "question": "Can you tell me your name?"},
            {"type": "perform_primary_survey", "target": "survivor_pari"},
            {"type": "treat_survivor", "target": "survivor_pari", "treatment": "control_bleeding"},
            {"type": "treat_survivor", "target": "survivor_pari", "treatment": "support_breathing"},
            {"type": "treat_survivor", "target": "survivor_pari", "treatment": "stabilise"},
            {"type": "free_survivor", "target": "survivor_pari"},
            {"type": "evacuate_survivor", "target": "survivor_pari"},
        ]
        self.index = 0
        self.fallback = RecommendedActionAgent()

    def act(self, observation):
        if self.index < len(self.bootstrap_plan):
            planned = parse_action(self.bootstrap_plan[self.index])
            self.index += 1
            return planned
        return self.fallback.act(observation)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a QuakeBot rescue episode.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--llm", action="store_true", help="Use optional OpenAI-compatible agent.")
    group.add_argument("--openai", action="store_true", help="Use optional OpenAI-compatible agent.")
    group.add_argument("--ollama", action="store_true", help="Use local Ollama agent.")
    group.add_argument("--ollama-cloud", action="store_true", help="Use Ollama Cloud with OLLAMA_API_KEY.")
    parser.add_argument(
        "--ollama-model",
        default=None,
        help="Ollama model name, defaults to OLLAMA_MODEL, gpt-oss:120b for cloud, or llama3.1 locally.",
    )
    parser.add_argument("--step", action="store_true", help="Wait for Enter before each episode step.")
    parser.add_argument(
        "--approximate",
        action="store_true",
        help="Use approximate survivor count mode; reachable rooms must be searched before final report.",
    )
    parser.add_argument("--random-events", action="store_true", help="Enable seeded dynamic world events.")
    parser.add_argument("--seed", type=int, default=7, help="Seed for random events when enabled.")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Specific scenario config (hidden_survivors_exact, hidden_survivors_approximate, generated_small, severe_risk_bleeding_survivor).",
    )
    parser.add_argument("--save-json", type=str, default=None, help="Save the episode to a JSON file.")
    args = parser.parse_args()

    agent_kind = "mock"
    if args.llm or args.openai:
        agent_kind = "openai"
    elif args.ollama:
        agent_kind = "ollama"
    elif args.ollama_cloud:
        agent_kind = "ollama-cloud"
    run_episode(
        agent_kind=agent_kind,
        ollama_model=args.ollama_model,
        wait_for_enter=args.step,
        approximate=args.approximate,
        random_events=args.random_events,
        seed=args.seed,
        scenario=args.scenario,
        save=args.save_json,
    )


if __name__ == "__main__":
    main()
