"""Maintenance copilot: turns a prediction into something a crew can act on.

The model output an operator actually sees is a fault label, a conformal set and
a list of feature contributions. That is evidence, not instruction. This service
turns it into a work order in Korean and English, grounded strictly in what the
system already knows.

Three constraints shape the design:

**It is grounded, not generative.** The prompt supplies the event's measured
values, the model's own attribution, and the decoded Sehwa maintenance-code
table. The system prompt forbids inventing procedures, part numbers or
tolerances that are not in that context. A copilot that confabulates a torque
spec for a 기억쇠 is worse than no copilot.

**It is never on a safety path.** Point machines are safety-critical signalling
equipment. This drafts paperwork and suggests what to inspect; it does not
authorise train movements, clear a route, or declare a machine fit for service.
That is stated in the system prompt and repeated in the response.

**It works without an API key.** A reviewer who clones this repository has no
`ANTHROPIC_API_KEY`, and a demo that shows an error box is a demo that does not
work. The deterministic drafter below builds the same work order from the same
grounded context, so the feature degrades to "less fluent" rather than "absent".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..config import settings

MODEL = "claude-opus-5"

#: The decoded Sehwa maintenance codes. Component names, not failure modes -
#: see docs/DATA.md. The copilot may cite these and nothing else.
MAINTENANCE_CODES: dict[str, tuple[str, str, str]] = {
    "E01": ("기억쇠", "Locking latch (memory cam)", "lock"),
    "E02": ("디텍터", "Detector rod", "detection"),
    "E03": ("무극선조계전기", "Non-polarised line relay", "control"),
    "E04": ("전동기", "Electric motor", "motor"),
    "E05": ("제어계전기", "Control relay", "control"),
    "E06": ("케이블", "Cable", "power"),
    "E07": ("회로제어기", "Circuit controller", "indication"),
}

#: What to physically inspect for each subsystem. Deliberately generic - these
#: are inspection prompts drawn from the signal's own meaning, not a maintenance
#: manual we do not have. Anything more specific would be invented.
SUBSYSTEM_CHECKS: dict[str, tuple[str, str]] = {
    "lock": (
        "쇄정 상태와 기억쇠 마모 확인. 전환 완료 후 표시 접점이 동작하는지 점검.",
        "Inspect the locking latch for wear and confirm the indication contacts "
        "make after the throw completes.",
    ),
    "detection": (
        "디텍터 로드 정렬 및 밀착 상태 확인.",
        "Check detector rod alignment and switch-rail closure against the stock rail.",
    ),
    "control": (
        "제어 회로 계전기 접점 및 배선 확인.",
        "Inspect control-circuit relay contacts and wiring.",
    ),
    "motor": (
        "전동기 브러시, 베어링, 기동 전류 확인.",
        "Inspect motor brushes and bearings; check starting current against the "
        "healthy reference.",
    ),
    "power": (
        "전원 케이블 접속부 저항 및 전압 강하 확인.",
        "Check supply cable terminations for resistance and measure volt-drop under load.",
    ),
    "indication": (
        "회로제어기 접점 채터링 확인.",
        "Inspect the circuit controller contact bank for chatter.",
    ),
    "mechanical": (
        "전환 경로 장애물 및 윤활 상태 확인.",
        "Clear the throw path of obstructions and check lubrication.",
    ),
    "-": ("특이사항 없음.", "No specific subsystem indicated."),
}

SYSTEM_PROMPT = """You are a maintenance copilot for railway point machines \
(선로전환기) on a Korean network. You draft work orders and answer questions from \
maintenance staff.

GROUNDING - this is the most important rule. You may only use:
  - the measured signal values supplied in the context
  - the model's own fault prediction, conformal prediction set and feature attributions
  - the Sehwa maintenance-code table supplied in the context

You must NOT invent part numbers, torque values, clearance tolerances, procedure \
step numbers, or any figure that is not in the context. If a crew would need a \
specification you were not given, say which specification they need to look up \
rather than supplying a number. Saying "check the maintenance manual for the \
closure tolerance" is correct; inventing "1.5 mm" is not.

SAFETY - you are decision support only. You never authorise a train movement, \
clear a route, release an interlocking, or declare a machine fit for service. If \
asked to do any of those, say that it is the signaller's or the responsible \
engineer's decision, and give them the evidence instead.

UNCERTAINTY - the conformal prediction set is the model's honest uncertainty. If \
it contains more than one label, say so plainly and describe what would \
distinguish them, rather than presenting the top label as settled.

STYLE - write for a maintenance technician on shift. Be specific and brief. Lead \
with what to check first. Use the Korean component name alongside the English one \
where a code is cited."""


@dataclass
class CopilotReply:
    answer: str
    source: str          # "claude" | "deterministic"
    model: str | None
    grounded_on: dict[str, Any]
    citations: list[str]
    disclaimer: str


DISCLAIMER_EN = (
    "Decision support only. Not a safety authority: this does not authorise a "
    "train movement or declare a machine fit for service."
)
DISCLAIMER_KO = (
    "참고용 보조 정보입니다. 열차 운행 허가나 사용 가능 판정을 대체하지 않습니다."
)


def _fmt(v: Any, digits: int = 2) -> str:
    return f"{v:.{digits}f}" if isinstance(v, (int, float)) else str(v)


def build_context(event: dict, machine: dict | None) -> dict[str, Any]:
    """Everything the copilot is allowed to reason from, and nothing else."""
    pred = event.get("prediction", {})
    code = pred.get("err_code") or ""
    ko, en, subsystem = MAINTENANCE_CODES.get(code, ("", "", "-"))
    return {
        "event_id": event.get("id"),
        "machine_id": event.get("machine_id"),
        "direction": event.get("direction"),
        "n_samples": event.get("n_samples"),
        "fault": pred.get("fault"),
        "fault_ko": pred.get("fault_ko"),
        "confidence": pred.get("confidence"),
        "prediction_set": pred.get("prediction_set", []),
        "severity": pred.get("severity"),
        "anomaly_score": pred.get("anomaly_score"),
        "err_code": code,
        "component_ko": ko,
        "component_en": en,
        "subsystem": subsystem,
        "phases": event.get("phases", []),
        "attributions": event.get("attributions", [])[:6],
        "health": (machine or {}).get("health"),
        "rul_cycles": (machine or {}).get("rul_cycles"),
        "rul_low": (machine or {}).get("rul_low"),
        "rul_high": (machine or {}).get("rul_high"),
    }


def _context_block(ctx: dict[str, Any]) -> str:
    lines = [
        f"Event {ctx['event_id']} on machine {ctx['machine_id']}, "
        f"commanded to {ctx['direction']}, {ctx['n_samples']} samples captured.",
        f"Model prediction: {ctx['fault']} ({ctx['fault_ko']}), "
        f"confidence {_fmt(ctx['confidence'])}, severity {ctx['severity']}.",
    ]
    ps = ctx.get("prediction_set") or []
    if len(ps) > 1:
        lines.append(
            f"Conformal prediction set at 90% coverage contains {len(ps)} labels: "
            f"{', '.join(ps)}. The model cannot rule these out."
        )
    elif ps:
        lines.append(f"Conformal prediction set contains only {ps[0]}.")
    if ctx["err_code"]:
        lines.append(
            f"Sehwa maintenance code {ctx['err_code']} = {ctx['component_ko']} "
            f"({ctx['component_en']}), subsystem: {ctx['subsystem']}."
        )
    if ctx.get("health") is not None:
        lines.append(f"Machine health index: {_fmt(ctx['health'])} (1.0 = as-new).")
    if ctx.get("rul_cycles") is not None:
        lines.append(
            f"Estimated remaining useful life: {_fmt(ctx['rul_cycles'], 0)} throws "
            f"(90% interval {_fmt(ctx.get('rul_low'), 0)} to {_fmt(ctx.get('rul_high'), 0)})."
        )
    if ctx.get("attributions"):
        lines.append("Evidence the model actually used, strongest first:")
        for a in ctx["attributions"]:
            lines.append(
                f"  - {a.get('feature')}: measured {_fmt(a.get('value'))}, "
                f"contribution {_fmt(a.get('contribution'), 3)}"
            )
    if ctx.get("phases"):
        spans = ", ".join(f"{p.get('name')} {p.get('start')}-{p.get('end')}" for p in ctx["phases"])
        lines.append(f"Throw phases (sample indices): {spans}.")
    lines.append(
        "\nThe full maintenance-code table you may cite:\n"
        + "\n".join(f"  {c} = {k} ({e})" for c, (k, e, _) in MAINTENANCE_CODES.items())
    )
    return "\n".join(lines)


def _deterministic(ctx: dict[str, Any], question: str | None) -> str:
    """A grounded work order with no model in the loop.

    Built from the same context the prompt would have received, so a reviewer
    without an API key sees the real shape of the feature rather than an error.
    """
    ko_check, en_check = SUBSYSTEM_CHECKS.get(ctx["subsystem"], SUBSYSTEM_CHECKS["-"])
    ps = ctx.get("prediction_set") or []
    out: list[str] = []

    out.append(f"## 작업 지시 / Work order — {ctx['machine_id']}")
    out.append("")
    out.append(f"**Detected / 감지:** {ctx['fault_ko'] or ctx['fault']} ({ctx['fault']})")
    if ctx["err_code"]:
        out.append(
            f"**Component / 부품:** {ctx['err_code']} · {ctx['component_ko']} "
            f"({ctx['component_en']})"
        )
    out.append(f"**Confidence / 신뢰도:** {_fmt(ctx['confidence'])}")

    if len(ps) > 1:
        out.append("")
        out.append(
            f"> The model cannot narrow this below {len(ps)} possibilities at 90% "
            f"coverage: **{', '.join(ps)}**. Treat the lead diagnosis as provisional."
        )
        out.append(f"> 90% 신뢰수준에서 {len(ps)}개 후보가 남아 있습니다.")

    out.append("")
    out.append("### 점검 사항 / What to check")
    out.append(f"1. {en_check}")
    out.append(f"   {ko_check}")

    if ctx.get("attributions"):
        top = ctx["attributions"][0]
        out.append(
            f"2. The strongest single piece of evidence was **{top.get('feature')}** "
            f"(measured {_fmt(top.get('value'))}). Compare it against this machine's "
            f"healthy reference before replacing anything."
        )

    if ctx.get("rul_cycles") is not None:
        out.append("")
        out.append("### 잔여 수명 / Remaining life")
        out.append(
            f"Estimated **{_fmt(ctx['rul_cycles'], 0)} throws** remaining "
            f"(90% interval {_fmt(ctx.get('rul_low'), 0)}–{_fmt(ctx.get('rul_high'), 0)}). "
            f"Health index {_fmt(ctx.get('health'))}."
        )

    if question:
        out.append("")
        out.append("### 질문 / Question")
        out.append(
            f"> {question}\n\n"
            "This draft was generated without the language model (no API key "
            "configured), so it cannot answer free-form questions. The evidence "
            "above is what the system has."
        )

    out.append("")
    out.append(f"_{DISCLAIMER_EN}_")
    out.append(f"_{DISCLAIMER_KO}_")
    return "\n".join(out)


def _has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def answer(event: dict, machine: dict | None, question: str | None = None) -> CopilotReply:
    """Draft a work order, or answer a question about this event."""
    ctx = build_context(event, machine)
    citations = [ctx["err_code"]] if ctx["err_code"] else []

    if not (settings.copilot_enabled and _has_credentials()):
        return CopilotReply(
            answer=_deterministic(ctx, question),
            source="deterministic",
            model=None,
            grounded_on=ctx,
            citations=citations,
            disclaimer=DISCLAIMER_EN,
        )

    try:
        import anthropic

        client = anthropic.Anthropic()
        user_text = _context_block(ctx)
        user_text += (
            f"\n\nThe technician asks: {question}"
            if question
            else "\n\nDraft the work order for this event, in Korean and English."
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user_text}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined this request")
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            raise RuntimeError("model returned no text")
        return CopilotReply(
            answer=text,
            source="claude",
            model=MODEL,
            grounded_on=ctx,
            citations=citations,
            disclaimer=DISCLAIMER_EN,
        )
    except Exception as exc:  # noqa: BLE001 - any failure must still produce a draft
        # An operations console must not lose a feature because a network call
        # failed. Fall back to the grounded draft and say which path produced it.
        print(f"[copilot] falling back to the deterministic draft: {exc}")
        return CopilotReply(
            answer=_deterministic(ctx, question),
            source="deterministic",
            model=None,
            grounded_on=ctx,
            citations=citations,
            disclaimer=DISCLAIMER_EN,
        )
