import argparse
from pathlib import Path

from quentin.orchestrator.daemon import OrchestratorDaemon
from quentin.orchestrator.default_tasks import build_default_tasks
from scripts.blueprint_self_iterate import create_runtime_for_blueprint_self_iteration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Meta-Agent orchestrator daemon."
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Polling interval in seconds between task checks.",
    )
    args = parser.parse_args()

    repo_root = Path(".").resolve()
    runtime = create_runtime_for_blueprint_self_iteration(repo_root=repo_root)

    orchestrator = OrchestratorDaemon(poll_interval_seconds=args.poll_interval)
    for task in build_default_tasks(runtime):
        orchestrator.register_task(task)

    print("Starting orchestrator daemon...")
    orchestrator.run_forever()
    print("Orchestrator daemon stopped.")


if __name__ == "__main__":
    main()
