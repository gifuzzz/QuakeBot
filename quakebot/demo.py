"""Runnable QuakeBot demo episode."""

from __future__ import annotations

import argparse

from .agents import MockAgent, OllamaAgent, OpenAIAgent
from .env import QuakeBotEnv
from .renderer import format_step, format_transcript


def run_episode(
    *,
    agent_kind: str = "mock",
    ollama_model: str | None = None,
    wait_for_enter: bool = False,
) -> QuakeBotEnv:
    env = QuakeBotEnv()
    if agent_kind == "openai":
        agent = OpenAIAgent()
    elif agent_kind == "ollama":
        agent = OllamaAgent(model=ollama_model)
    elif agent_kind == "ollama-cloud":
        agent = OllamaAgent(model=ollama_model, cloud=True)
    else:
        agent = MockAgent()

    if isinstance(agent, OpenAIAgent) and not agent.available:
        print("OPENAI_API_KEY is not set; falling back to MockAgent.")
        agent = MockAgent()
    if isinstance(agent, OllamaAgent) and not agent.available:
        if agent.cloud:
            print("Ollama Cloud is not available. Set OLLAMA_API_KEY; falling back to MockAgent.")
        else:
            print("Ollama is not reachable at OLLAMA_HOST; falling back to MockAgent.")
        agent = MockAgent()

    transcript: list[str] = []
    while not env.done:
        observation = env.observe()
        if wait_for_enter:
            input(f"Press Enter for step {env.step_count + 1}...")
        action = agent.act(observation)
        result = env.step(action)
        entry = format_step(env.step_count, observation, action, result)
        transcript.append(entry)
        print(entry)
        print()

    print(format_transcript(transcript, env.final_report, env.score.total))
    return env


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
    args = parser.parse_args()

    agent_kind = "mock"
    if args.llm or args.openai:
        agent_kind = "openai"
    elif args.ollama:
        agent_kind = "ollama"
    elif args.ollama_cloud:
        agent_kind = "ollama-cloud"
    run_episode(agent_kind=agent_kind, ollama_model=args.ollama_model, wait_for_enter=args.step)


if __name__ == "__main__":
    main()
