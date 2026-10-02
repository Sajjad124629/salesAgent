#!/usr/bin/env python3
import bootstrap
import sys
import os
import argparse
from agent import ScoutAgent
from evals import run_evals
from config import RUNS_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Scout: An autonomous lead-finding AI agent built from scratch in pure Python.",
        usage="python scout.py [run | resume <run_id> | eval]"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Start a new live agent run to find leads")
    run_parser.add_argument(
        "--goal",
        type=str,
        default="Find active leads on Reddit (Upwork, freelance, Daytrading, sales) who need fast notifications, research them, and draft replies for approval.",
        help="Optional custom objective for Scout"
    )

    # Command: resume
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted run from a checkpoint")
    resume_parser.add_argument("run_id", type=str, help="The ID of the run to resume (e.g. run_1727788800)")

    # Command: eval
    eval_parser = subparsers.add_parser("eval", help="Run the accuracy and security evaluation benchmark")
    eval_parser.add_argument("--samples", type=int, default=41, help="Number of items from eval_set to test")

    args = parser.parse_args()

    if args.command == "run":
        agent = ScoutAgent()
        agent.run(initial_user_goal=args.goal)

    elif args.command == "resume":
        run_id = args.run_id
        checkpoint_path = os.path.join(RUNS_DIR, run_id, "state.json")
        if not os.path.exists(checkpoint_path):
            print(f"Error: Checkpoint file not found for run '{run_id}' at {checkpoint_path}")
            sys.exit(1)

        print(f"\nResuming run {run_id} from saved checkpoint...")
        agent = ScoutAgent(run_id=run_id)
        if not agent.load_checkpoint():
            print(f"Failed to load checkpoint for run {run_id}.")
            sys.exit(1)
        print(f"Loaded run {run_id}: Step {agent.step}, Tokens so far: {agent.total_tokens}, Cost so far: ${agent.total_cost:.4f}")
        agent.run()

    elif args.command == "eval":
        run_evals(sample_limit=args.samples)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
