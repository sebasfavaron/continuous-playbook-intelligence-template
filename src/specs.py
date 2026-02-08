from __future__ import annotations

from .cluster import Cluster


def _guess_trigger(signals: list[str]) -> str:
    text = " ".join(signals)
    if "wf:deploy" in text:
        return "When a user asks to deploy/release a project"
    if "wf:debug" in text:
        return "When a user asks to investigate failures or fix errors"
    if "git" in text:
        return "When a user asks for repeated repository maintenance steps"
    return "When a user repeats a similar multi-step operational workflow"


def _workflow_steps(signals: list[str]) -> list[str]:
    steps = [
        "Validate repository and environment prerequisites.",
        "Plan command sequence based on detected workflow intent.",
    ]
    if any("git" in s for s in signals):
        steps.append("Run repository status and branch synchronization steps.")
    if any("pytest" in s or "wf:test" in s for s in signals):
        steps.append("Execute targeted tests and collect failures.")
    if any("wf:deploy" in s or "aws" in s or "gcloud" in s for s in signals):
        steps.append("Run deployment pipeline with staged verification checks.")
    if any("ssh" in s for s in signals):
        steps.append("Execute remote verification commands and capture diagnostics.")
    steps.extend(
        [
            "Summarize results and produce a structured action/result report.",
            "On failure, emit remediation guidance and safe retry instructions.",
        ]
    )
    return steps


def build_automation_spec(cluster: Cluster) -> dict:
    signals = cluster.representative_signals
    return {
        "goal": f"Automate repeated workflow pattern: {', '.join(signals[:4])}",
        "trigger": _guess_trigger(signals),
        "inputs": [
            "repository_path",
            "target_environment",
            "operation_parameters",
        ],
        "workflow_steps": _workflow_steps(signals),
        "expected_outputs": [
            "execution_summary",
            "structured_logs",
            "next_actions",
        ],
        "failure_modes": [
            "missing_prerequisites",
            "permission_denied",
            "command_failure",
            "non_deterministic_output",
        ],
        "guardrails": [
            "require_non_destructive_default_actions",
            "require_explicit_confirmation_for_destructive_operations",
            "capture_before_after_state_for_critical_steps",
        ],
        "acceptance_tests": [
            "replays_known_workflow_and_produces_expected_artifacts",
            "fails_safely_with_actionable_error_when_prerequisites_missing",
            "produces_deterministic_summary_for_same_input",
        ],
    }
