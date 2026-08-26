"""Run offline evaluations on the Chat LangChain Lite agent.

Used locally and in CI/CD (GitHub Actions runs this on every PR).
Exits with code 1 if average scores fall below --threshold.

Usage:
    python -m scripts.run_evals                          # full run, create/update dataset
    python -m scripts.run_evals --skip-dataset           # reuse existing dataset (CI default)
    python -m scripts.run_evals --threshold 0.8          # fail if scores below 0.8
    python -m scripts.run_evals --no-generated           # skip LLM-generated examples
    python -m scripts.run_evals --setup-online-eval      # also set up online evaluator
"""

import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

from evals.dataset import DATASET_NAME, DEMO_PRESENTER
PROJECT_NAME = os.getenv("LANGSMITH_PROJECT", "chat-lc-lite")



def _git(*args: str) -> str | None:
    """Read local git state; returns None outside a repo."""
    import subprocess
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def experiment_metadata(threshold: float | None) -> dict:
    """Provenance for the experiment, so the Experiments panel answers
    "which commit was this, and did the gate pass?" without leaving LangSmith.

    In CI these come from the GitHub Actions context; locally they fall back to
    the working tree. Every value lands as a filterable metadata column.
    """
    in_ci = os.getenv("GITHUB_ACTIONS") == "true"
    sha = os.getenv("GITHUB_SHA") or _git("rev-parse", "HEAD")
    branch = os.getenv("GITHUB_HEAD_REF") or os.getenv("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD")
    md = {
        "demo": "true",
        "demo_type": "chat-lc-lite",
        "source": "ci" if in_ci else "local",
        "git_branch": branch,
        "git_sha": sha,
        "git_sha_short": (sha or "")[:8] or None,
        "git_dirty": bool(_git("status", "--porcelain")) if not in_ci else False,
        "threshold": threshold,
    }
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    pr = os.getenv("PR_NUMBER") or ""
    if pr.isdigit():
        md["pr_number"] = int(pr)
        if repo:
            md["pr_url"] = f"https://github.com/{repo}/pull/{pr}"
    if repo and run_id:
        md["ci_run_url"] = f"https://github.com/{repo}/actions/runs/{run_id}"
    return {k: v for k, v in md.items() if v is not None}


def run_agent_on_example(inputs: dict) -> dict:
    from agent.agent import invoke_agent
    question = (inputs.get("question") or "").strip()
    if not question:
        # Engine-generated examples use chat message format
        messages = inputs.get("messages") or inputs.get("input") or []
        if isinstance(messages, list):
            for msg in messages:
                role = msg.get("role", "") if isinstance(msg, dict) else ""
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                if role in ("human", "user") and content:
                    question = content.strip()
                    break
    if not question:
        return {"output": "", "tools_called": []}
    result = invoke_agent(question=question)
    return {"output": result["output"], "tools_called": result.get("tools_called", [])}


def run_evaluation(experiment_prefix: str, threshold: float | None = None) -> dict:
    from langsmith import evaluate
    from evals.evaluators import assertion_evaluator

    print(f"\nRunning evaluation on dataset '{DATASET_NAME}'...")

    results = evaluate(
        run_agent_on_example,
        data=DATASET_NAME,
        evaluators=[assertion_evaluator],
        experiment_prefix=experiment_prefix,
        metadata=experiment_metadata(threshold),
    )

    # One feedback per example: assertion_evaluator returns
    # {key: "assertions_pass_rate", score: 0.0..1.0}. Overall is the mean
    # across examples — i.e. the average fraction of assertions met.
    per_example: list[float] = []
    for result in results:
        for ev in result.get("evaluation_results", {}).get("results", []):
            if ev.score is None:
                continue
            per_example.append(ev.score)

    overall = sum(per_example) / len(per_example) if per_example else 0.0
    n = len(per_example)

    # Stamp the gate verdict onto the experiment so the Experiments panel shows
    # pass/fail per commit, not just a number the viewer has to compare by eye.
    if threshold is not None:
        try:
            from langsmith import Client
            exp_name = getattr(results, "experiment_name", None)
            if exp_name:
                client = Client()
                proj = next((p for p in client.list_projects(name=exp_name)), None)
                if proj:
                    client.update_project(
                        proj.id,
                        metadata={**(proj.metadata or {}),
                                  "gate": "PASS" if overall >= threshold else "FAIL"},
                    )
        except Exception as e:  # never fail a run over bookkeeping
            print(f"  (could not stamp gate verdict: {type(e).__name__})")
    print(f"\nResults:")
    print(f"  assertions_pass_rate  {overall:.2f}  (avg across {n} examples)")
    return {"assertions_pass_rate": overall, "__overall__": overall}


def check_threshold(scores: dict, threshold: float) -> bool:
    """Returns True if the overall assertion pass rate meets the threshold."""
    overall = scores.get("__overall__", 0.0)
    status = "✅ PASS" if overall >= threshold else "❌ FAIL"
    print(f"\nThreshold check (overall pass rate >= {threshold}):")
    print(f"  overall: {overall:.2f} {status}")
    return overall >= threshold


ONLINE_EVALUATORS = [
    {
        "display_name": "chat-lc-lite-demo-security-advice-online",
        "feedback_key": "security_advice",
        "system_prompt": (
            "You are evaluating whether a Chat LangChain Lite assistant gave safe, accurate "
            "guidance. The agent must NEVER recommend or link to python.langchain.com or "
            "js.langchain.com — those are STALE doc domains. Canonical = docs.langchain.com.\n\n"
            "Score 1 if the agent's response uses only docs.langchain.com links. "
            "Score 0 if it recommended python.langchain.com or js.langchain.com as a source."
        ),
    },
    {
        "display_name": "chat-lc-lite-demo-scope-adherence-online",
        "feedback_key": "scope_adherence",
        "system_prompt": (
            "You are evaluating whether a Chat LangChain Lite assistant stayed on topic.\n\n"
            "Did the agent refuse to answer questions outside the LangChain ecosystem "
            "(LangChain, LangGraph, LangSmith, Deep Agents) and stay focused on those topics?"
        ),
    },
]


def setup_online_eval():
    import requests
    from langchain_anthropic import ChatAnthropic

    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        print("Warning: LANGSMITH_API_KEY not set, skipping online eval setup.")
        return

    from langsmith import Client
    ls_client = Client()

    projects = list(ls_client.list_projects())
    project = next((p for p in projects if p.name == PROJECT_NAME), None)
    if not project:
        print(f"Warning: Project '{PROJECT_NAME}' not found. Generate some traces first.")
        return

    print(f"\nSetting up online evaluators on project '{PROJECT_NAME}'...")

    model_json = ChatAnthropic(model="claude-haiku-4-5-20251001").to_json()

    for ev in ONLINE_EVALUATORS:
        payload = {
            "display_name": ev["display_name"],
            "session_id": str(project.id),
            "sampling_rate": 1.0,
            "evaluators": [
                {
                    "structured": {
                        "prompt": [
                            ["system", ev["system_prompt"]],
                            ["human", "Agent response: {{output}}"],
                        ],
                        "variable_mapping": {"output": "output"},
                        "model": model_json,
                        "schema": {
                            "title": "score_run",
                            "type": "object",
                            "properties": {
                                ev["feedback_key"]: {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 1,
                                    "description": "1 = pass, 0 = fail",
                                },
                            },
                            "required": [ev["feedback_key"]],
                        },
                    }
                }
            ],
        }

        resp = requests.post(
            "https://api.smith.langchain.com/api/v1/runs/rules",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )

        if resp.status_code in (200, 201):
            print(f"  ✅ Created '{ev['display_name']}' (feedback key: '{ev['feedback_key']}')")
        else:
            print(f"  ⚠️  '{ev['display_name']}' returned {resp.status_code}: {resp.text[:200]}")

    print("\nOnce set up, LangSmith will automatically score all new traces in the project.")
    print("Scores will appear as 'security_advice' and 'scope_adherence' feedback on each trace.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dataset", action="store_true", help="Reuse existing dataset (used in CI)")
    parser.add_argument("--no-generated", action="store_true")
    parser.add_argument("--n-generated", type=int, default=8)
    parser.add_argument("--setup-online-eval", action="store_true")
    parser.add_argument("--threshold", type=float, default=None, help="Fail (exit 1) if avg score below this value")
    parser.add_argument("--experiment-prefix", type=str, default=f"engine-chat-lc-lite-{DEMO_PRESENTER}")
    args = parser.parse_args()

    if not args.skip_dataset:
        from evals.dataset import create_or_update_dataset
        print(f"Preparing dataset '{DATASET_NAME}'...")
        create_or_update_dataset()

    scores = run_evaluation(experiment_prefix=args.experiment_prefix, threshold=args.threshold)

    if args.setup_online_eval:
        setup_online_eval()

    print(f"\nView results: https://smith.langchain.com — project '{PROJECT_NAME}'")

    if args.threshold is not None:
        passed = check_threshold(scores, args.threshold)
        if not passed:
            print("\nEvals failed — scores below threshold. Blocking merge.")
            sys.exit(1)
        else:
            print("\nAll evals passed. ✅")


if __name__ == "__main__":
    main()
