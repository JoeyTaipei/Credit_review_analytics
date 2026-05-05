"""
agent_trace.py
==============
Layer 5: Agent Trace

Records every step of the pipeline / agent execution as a structured log.
This is what separates a "data analyst script" from a "production-grade
AI system" in a Deloitte interview.

Why this layer matters
----------------------
1. Observability: you can replay what happened for any run_id
2. Debugging: if a step fails you know exactly where and why
3. Audit trail: regulators can ask "what did the AI do for company X?"
4. Latency profiling: find bottlenecks before production
5. Confidence tracking: downstream steps can see if upstream succeeded

This is a lightweight version of what LangSmith provides for LangChain agents.
In Day 5, when we wire up the LangChain agent, traces from both systems
will share the same run_id so you can correlate pipeline steps with agent calls.

Schema
------
run_id          : UUID for the full pipeline run
company_id      : ticker being analysed (None for portfolio-level steps)
step_name       : e.g. "load_data", "engineer_features", "detect_anomaly"
tool_used       : e.g. "pandas", "sklearn", "anthropic_api"
input_data_ref  : description of what went in (not the data itself)
output_data_ref : description of what came out
status          : success | fail | retry | skipped
latency_ms      : wall-clock milliseconds
confidence_score: optional 0-1, used for ML/LLM steps
error_message   : populated on fail
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TraceStep:
    run_id:           str
    company_id:       Optional[str]
    step_name:        str
    tool_used:        str
    input_data_ref:   str
    output_data_ref:  str
    status:           str          # success | fail | retry | skipped
    latency_ms:       float
    confidence_score: Optional[float] = None
    error_message:    Optional[str]   = None
    timestamp:        str = field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentTracer:
    """
    Collects trace steps during a pipeline run.

    Usage
    -----
    tracer = AgentTracer()

    with tracer.step("load_data", tool="pandas", company_id=None,
                     input_ref="sample_financials_long.csv",
                     output_ref="DataFrame(45 rows)") as ctx:
        df = load_financials()
        ctx.set_output("DataFrame(45, 26 columns)")

    tracer.save("outputs/agent_trace.csv")
    """

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or str(uuid.uuid4())[:8]
        self._steps: list[TraceStep] = []

    # ------------------------------------------------------------------
    # Context manager for a single step
    # ------------------------------------------------------------------

    @contextmanager
    def step(
        self,
        step_name: str,
        tool: str,
        input_ref: str,
        output_ref: str = "pending",
        company_id: Optional[str] = None,
        confidence: Optional[float] = None,
    ):
        """
        Usage:
            with tracer.step("detect_anomaly", tool="zscore",
                             input_ref="features(45,9)") as ctx:
                result = detect_anomalies(features)
                ctx.set_output(f"anomalies({result.shape})")
                ctx.set_confidence(0.82)
        """
        start = time.perf_counter()
        ctx = _StepContext(output_ref, confidence)

        try:
            yield ctx
            status = "success"
            error  = None
        except Exception as exc:
            status = "fail"
            error  = str(exc)
            raise
        finally:
            latency = (time.perf_counter() - start) * 1000
            self._steps.append(TraceStep(
                run_id           = self.run_id,
                company_id       = company_id,
                step_name        = step_name,
                tool_used        = tool,
                input_data_ref   = input_ref,
                output_data_ref  = ctx._output_ref,
                status           = status,
                latency_ms       = round(latency, 1),
                confidence_score = ctx._confidence,
                error_message    = error,
            ))

    # ------------------------------------------------------------------
    # Simple log (for steps that don't need timing)
    # ------------------------------------------------------------------

    def log(
        self,
        step_name: str,
        tool: str,
        input_ref: str,
        output_ref: str,
        company_id: Optional[str] = None,
        status: str = "success",
        latency_ms: float = 0.0,
        confidence: Optional[float] = None,
    ) -> None:
        self._steps.append(TraceStep(
            run_id=self.run_id, company_id=company_id,
            step_name=step_name, tool_used=tool,
            input_data_ref=input_ref, output_data_ref=output_ref,
            status=status, latency_ms=latency_ms, confidence_score=confidence,
        ))

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(s) for s in self._steps])

    def save(self, path: str | Path) -> None:
        df = self.to_dataframe()
        df.to_csv(path, index=False)

    def summary(self) -> str:
        df = self.to_dataframe()
        total   = len(df)
        success = (df["status"] == "success").sum()
        failed  = (df["status"] == "fail").sum()
        total_ms = df["latency_ms"].sum()
        return (
            f"Run {self.run_id}: {total} steps | "
            f"{success} success | {failed} fail | "
            f"{total_ms:.0f}ms total"
        )


class _StepContext:
    """Mutable context yielded inside the `with tracer.step(...)` block."""

    def __init__(self, output_ref: str, confidence: Optional[float]):
        self._output_ref = output_ref
        self._confidence = confidence

    def set_output(self, ref: str) -> None:
        self._output_ref = ref

    def set_confidence(self, score: float) -> None:
        self._confidence = score


# ---------------------------------------------------------------------------
# Human-in-the-loop table (Layer 6)
# ---------------------------------------------------------------------------

@dataclass
class HumanReview:
    """
    Records when a human reviewer overrides or confirms an AI decision.

    In production this would be a database table with an approval workflow.
    For demo, we produce a CSV that simulates what the UI would write.
    """
    review_id:       str
    run_id:          str
    company_id:      str
    ai_decision:     str        # what the AI recommended
    human_flag:      int        # 1 = human intervened, 0 = accepted AI output
    correction_type: str        # "upgrade" | "downgrade" | "confirmed" | "pending"
    final_decision:  str        # the actual decision after review
    review_time_sec: float
    reviewer_note:   str = ""
    timestamp:       str = field(default_factory=lambda: datetime.utcnow().isoformat())


def generate_sample_hitl(decisions_df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """
    Generates plausible simulated human-in-the-loop reviews.

    In a real system this table would be populated by the UI when a
    credit officer approves / modifies the AI recommendation.

    Rules used for simulation:
    - critical → human always reviews (may confirm or downgrade)
    - high     → human reviews 80% of the time
    - medium   → human reviews 30% of the time
    - low      → human reviews 5% (spot-check)
    """
    import random
    random.seed(42)

    rows = []
    for _, row in decisions_df.iterrows():
        level = row.get("final_risk_level", "low")
        review_prob = {"critical": 1.0, "high": 0.8, "medium": 0.3, "low": 0.05}.get(level, 0.05)

        if random.random() > review_prob:
            continue

        ai_action = row.get("recommended_action", "approve")
        # Simulate occasional human override
        if level in ("critical", "high") and random.random() < 0.3:
            human_flag = 1
            correction = "downgrade"   # human thinks AI was too harsh
            final = "monitor"
            note = "經辦評估後認為短期流動性壓力已改善，降為觀察"
        else:
            human_flag = 0
            correction = "confirmed"
            final = ai_action
            note = ""

        rows.append(HumanReview(
            review_id       = str(uuid.uuid4())[:8],
            run_id          = run_id,
            company_id      = str(row.get("ticker", "")),
            ai_decision     = ai_action,
            human_flag      = human_flag,
            correction_type = correction,
            final_decision  = final,
            review_time_sec = round(random.uniform(30, 600), 0),
            reviewer_note   = note,
        ))

    return pd.DataFrame([asdict(r) for r in rows]) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# CLI for demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tracer = AgentTracer()

    with tracer.step("load_data", tool="pandas",
                     input_ref="sample_financials_long.csv") as ctx:
        time.sleep(0.02)
        ctx.set_output("DataFrame(45, 26)")

    with tracer.step("engineer_features", tool="pandas",
                     input_ref="DataFrame(45, 26)") as ctx:
        time.sleep(0.05)
        ctx.set_output("DataFrame(45, 35) +9 feature cols")
        ctx.set_confidence(1.0)

    with tracer.step("detect_anomaly", tool="zscore_loo",
                     input_ref="DataFrame(45, 35)") as ctx:
        time.sleep(0.03)
        ctx.set_output("anomalies(108 rows, 29 flagged)")
        ctx.set_confidence(0.85)

    with tracer.step("compute_risk_flags", tool="rule_engine",
                     input_ref="DataFrame(45, 35)") as ctx:
        time.sleep(0.01)
        ctx.set_output("flags(5 cols) + anomaly_score + decision")
        ctx.set_confidence(1.0)

    with tracer.step("generate_summary", tool="anthropic_stub",
                     input_ref="CompanyAnalysisInput(2317)") as ctx:
        time.sleep(0.08)
        ctx.set_output("summary_text(280 chars)")
        ctx.set_confidence(0.78)

    df = tracer.to_dataframe()
    print(tracer.summary())
    print()
    print(df[["step_name", "tool_used", "status", "latency_ms", "confidence_score"]].to_string(index=False))
