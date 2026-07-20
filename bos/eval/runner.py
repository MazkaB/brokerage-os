"""
Eval harness for BOS KPIs.

Measures the three core PRD metrics:
  - Intent accuracy (>95% target)
  - Hallucination rate (<2% target) - cross-checks LLM response against
    worker tool data (numbers must match)
  - Task completion (>90% target) - graph completes without error

Datasets live in `eval/datasets/*.jsonl`. Each line is a scenario:
  {"message": "...", "expected_intent": "...", "expected_manager": "...",
   "expected_approval_required": bool, "must_contain": ["...", "..."],
   "must_not_contain": ["..."]}

Run:
    python -m eval.runner --dataset eval/datasets/scenarios.jsonl
    python -m eval.runner --dataset ... --limit 20   # quick subset
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

# Make app importable when running as `python -m eval.runner` from bos/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import build_bos_graph
from app.security import authenticate_user

log = logging.getLogger("bos.eval")


@dataclass
class ScenarioResult:
    scenario_id: str
    message: str
    expected_intent: str
    actual_intent: Optional[str]
    expected_manager: str
    actual_manager: Optional[str]
    intent_correct: bool
    manager_correct: bool
    approval_correct: bool
    completion: bool
    hallucination_flags: List[str] = field(default_factory=list)
    must_contain_hits: int = 0
    must_contain_total: int = 0
    final_response_snippet: str = ""
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class EvalReport:
    total: int
    intent_accuracy: float
    manager_accuracy: float
    approval_accuracy: float
    task_completion: float
    hallucination_rate: float
    avg_latency_ms: int
    pass_intent_target: bool  # >95%
    pass_completion_target: bool  # >90%
    pass_hallucination_target: bool  # <2%
    scenarios: List[ScenarioResult]


def load_dataset(path: Path) -> list:
    scenarios = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                s = json.loads(line)
                s["_id"] = s.get("id", f"S{i:03d}")
                scenarios.append(s)
            except json.JSONDecodeError as e:
                log.warning("skipping malformed scenario line %d: %s", i, e)
    return scenarios


def _extract_numbers(text: str) -> List[float]:
    """Extract all numeric values from a string for cross-checking."""
    if not text:
        return []
    matches = re.findall(r"-?\$?\d+(?:\.\d+)?", text.replace(",", ""))
    out = []
    for m in matches:
        try:
            out.append(float(m.replace("$", "")))
        except ValueError:
            pass
    return out


def _check_hallucination(response: str, worker_data: dict) -> List[str]:
    """Cross-check numbers in the response against worker data.

    Returns list of suspicious discrepancies (e.g. "mentioned $99.99 not in
    source data"). Empty list = no hallucination detected.
    """
    flags = []
    # Gather all "ground truth" numbers from worker outputs
    truth = set()
    for wname, wout in (worker_data or {}).items():
        wd = wout.get("data") or {}
        # Recursively collect numbers
        def _walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    _walk(v)
            elif isinstance(obj, (int, float)):
                truth.add(round(float(obj), 2))
        _walk(wd)

    if not truth:
        return []  # no ground truth to check against

    # For each number in response, check it's "close enough" to a truth value
    for n in _extract_numbers(response):
        if not any(abs(n - t) < 0.5 for t in truth):
            # Allow 50-cent tolerance for rounding
            flags.append(f"number {n} not in worker data")
    return flags


def run_scenario(graph, scenario: dict, auth) -> ScenarioResult:
    sid = scenario["_id"]
    msg = scenario["message"]
    expected_intent = scenario.get("expected_intent", "")
    expected_manager = scenario.get("expected_manager", "")
    expected_approval = scenario.get("expected_approval_required")

    import uuid
    thread_id = f"eval-{sid}-{uuid.uuid4().hex[:6]}"
    state = {
        "thread_id": thread_id, "user_message": msg,
        "user_id": auth.user_id, "username": auth.username, "role": auth.role,
        "permissions": list(auth.permissions), "user_profile": {},
    }
    config = {"configurable": {"thread_id": thread_id}}

    t0 = time.time()
    try:
        result = graph.invoke(state, config=config)
        latency_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        return ScenarioResult(
            scenario_id=sid, message=msg, expected_intent=expected_intent,
            actual_intent=None, expected_manager=expected_manager, actual_manager=None,
            intent_correct=False, manager_correct=False, approval_correct=False,
            completion=False, latency_ms=int((time.time() - t0) * 1000),
            error=str(e),
        )

    actual_intent = result.get("intent")
    actual_manager = result.get("manager")
    completion = bool(result.get("final_response"))

    # Approval check (only if expected)
    approval_correct = True
    if expected_approval is not None:
        snapshot = graph.get_state(config)
        needs_approval = (
            snapshot.next and "request_approval" in snapshot.next
            and any(getattr(t, "interrupts", None) for t in snapshot.tasks)
        )
        approval_correct = (needs_approval == expected_approval)

    # Hallucination check
    response = result.get("final_response") or ""
    worker_data = result.get("worker_outputs") or {}
    hall_flags = _check_hallucination(response, worker_data)

    # must_contain / must_not_contain
    must_contain = scenario.get("must_contain", []) or []
    hits = sum(1 for needle in must_contain if needle.lower() in response.lower())
    must_not_contain = scenario.get("must_not_contain", []) or []
    for forbidden in must_not_contain:
        if forbidden.lower() in response.lower():
            hall_flags.append(f"contained forbidden text: {forbidden}")

    return ScenarioResult(
        scenario_id=sid, message=msg, expected_intent=expected_intent,
        actual_intent=actual_intent, expected_manager=expected_manager,
        actual_manager=actual_manager,
        intent_correct=(actual_intent == expected_intent) if expected_intent else True,
        manager_correct=(actual_manager == expected_manager) if expected_manager else True,
        approval_correct=approval_correct,
        completion=completion,
        hallucination_flags=hall_flags,
        must_contain_hits=hits,
        must_contain_total=len(must_contain),
        final_response_snippet=response[:200],
        latency_ms=latency_ms,
    )


def run_eval(dataset_path: Path, limit: Optional[int] = None,
             output_path: Optional[Path] = None) -> EvalReport:
    """Run the eval harness against a dataset."""
    scenarios = load_dataset(dataset_path)
    if limit:
        scenarios = scenarios[:limit]

    log.info("Running eval: %d scenarios from %s", len(scenarios), dataset_path)
    graph = build_bos_graph()
    auth = authenticate_user("advisor@bos.local")

    results: List[ScenarioResult] = []
    for s in scenarios:
        log.info("Scenario %s: %s", s["_id"], s["message"][:60])
        r = run_scenario(graph, s, auth)
        results.append(r)
        log.info("  → intent=%s manager=%s completion=%s hall=%d",
                 r.actual_intent, r.actual_manager, r.completion, len(r.hallucination_flags))

    # Aggregate
    n = len(results)
    intent_acc = sum(1 for r in results if r.intent_correct) / max(n, 1)
    mgr_acc = sum(1 for r in results if r.manager_correct) / max(n, 1)
    appr_acc = sum(1 for r in results if r.approval_correct) / max(n, 1)
    completion = sum(1 for r in results if r.completion) / max(n, 1)
    # Hallucination rate = scenarios with ANY hallucination flag
    hall_scenarios = sum(1 for r in results if r.hallucination_flags)
    hall_rate = hall_scenarios / max(n, 1)
    avg_lat = sum(r.latency_ms for r in results) // max(n, 1)

    report = EvalReport(
        total=n,
        intent_accuracy=round(intent_acc, 4),
        manager_accuracy=round(mgr_acc, 4),
        approval_accuracy=round(appr_acc, 4),
        task_completion=round(completion, 4),
        hallucination_rate=round(hall_rate, 4),
        avg_latency_ms=avg_lat,
        pass_intent_target=intent_acc >= 0.95,
        pass_completion_target=completion >= 0.90,
        pass_hallucination_target=hall_rate <= 0.02,
        scenarios=results,
    )

    if output_path:
        out = {**asdict(report)}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, default=str)
        log.info("Report written to %s", output_path)

    return report


def print_summary(report: EvalReport) -> None:
    print()
    print("=" * 60)
    print(" BOS EVAL REPORT")
    print("=" * 60)
    print(f" Total scenarios:    {report.total}")
    print()
    print(f" Intent accuracy:    {report.intent_accuracy:.1%}  "
          f"(target ≥95%: {'PASS' if report.pass_intent_target else 'FAIL'})")
    print(f" Manager accuracy:   {report.manager_accuracy:.1%}")
    print(f" Approval accuracy:  {report.approval_accuracy:.1%}")
    print(f" Task completion:    {report.task_completion:.1%}  "
          f"(target ≥90%: {'PASS' if report.pass_completion_target else 'FAIL'})")
    print(f" Hallucination rate: {report.hallucination_rate:.1%}  "
          f"(target ≤2%:  {'PASS' if report.pass_hallucination_target else 'FAIL'})")
    print(f" Avg latency:        {report.avg_latency_ms} ms")
    print()
    failed = [s for s in report.scenarios if not (s.intent_correct and s.completion)]
    if failed:
        print(f" {len(failed)} scenarios with issues:")
        for s in failed[:5]:
            print(f"  - {s.scenario_id}: intent={s.actual_intent} "
                  f"(exp {s.expected_intent}), err={s.error or 'none'}")
    print("=" * 60)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="BOS eval harness")
    parser.add_argument("--dataset", required=True, help="Path to .jsonl scenarios file")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N scenarios")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    args = parser.parse_args()

    report = run_eval(Path(args.dataset), limit=args.limit,
                      output_path=Path(args.output) if args.output else None)
    print_summary(report)


if __name__ == "__main__":
    main()
