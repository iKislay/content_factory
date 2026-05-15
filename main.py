# main.py
"""
Content Factory — Multi-Agent Pipeline Entry Point

Launches the OrchestratorAgent which plans, routes work across specialist
agents, and drives the full pipeline from topic discovery to video publishing.

Usage:
    python main.py               # start new run or resume pending run
    python main.py --run <id>    # resume a specific run by ID
"""

import argparse
import sys
import os

import config
from state import PipelineState
from agents.orchestrator import OrchestratorAgent


def run_pipeline(run_id: str | None = None) -> None:
    """
    Initialize state and launch the Orchestrator.

    The Orchestrator handles everything from here:
      - Checks for a pending run (crash recovery)
      - Declares the execution plan
      - Dispatches TrendScout → Narrator → Production → Publisher
      - Reflects on each result before proceeding
      - Posts the full causal trace to the agent blackboard
    """
    # Ensure output directories exist
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    # Initialize state DB (creates tables if not exist)
    state = PipelineState()
    state.init_db()

    # Launch the Orchestrator
    orchestrator = OrchestratorAgent(state)
    result = orchestrator.run(run_id=run_id)

    if result.success:
        final_path = result.output.get("final_path", "")
        print(f"\n{'='*60}")
        print(f"  Pipeline complete ✓")
        print(f"  Output: {final_path}")
        print(f"{'='*60}\n")
        sys.exit(0)
    else:
        print(f"\n{'='*60}")
        print(f"  Pipeline FAILED ✗")
        print(f"  Errors: {result.errors}")
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Content Factory — Multi-Agent Video Pipeline"
    )
    parser.add_argument(
        "--run",
        metavar="RUN_ID",
        default=None,
        help="Resume a specific run by its UUID (optional)",
    )
    args = parser.parse_args()
    run_pipeline(run_id=args.run)