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

**It works without an API key.** By default it drafts with a local model through
Ollama — no key, no per-token bill — and anyone using the console may choose
among the models installed on the machine. The Claude API remains available to
an operator who configures it. Whatever fails, the deterministic drafter below
builds the same work order from the same grounded context, so the feature
degrades to "less fluent" rather than "absent", and says why it degraded.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from pmdlib.sim.spec import FAULT_META, FAULT_TO_ERR_CODE, FaultClass

from ..config import settings

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
distinguish them, rather than presenting the top label as settled. Direct checks \
at what the labels in the set describe; do not cite a maintenance code that no \
label in the set maps to.

STYLE - write for a maintenance technician on shift. Be specific and brief: a \
work order should fit in about 200 words. Lead with what to check first. Use the \
Korean component name alongside the English one where a code is cited. Write plain \
text with numbered steps, not Markdown - the console shows your text exactly as \
written, so asterisks and hashes appear as clutter."""


@dataclass
class CopilotReply:
    answer: str
    source: str          # "ollama" | "claude" | "deterministic"
    model: str | None
    #: Why a language model was not used, when it was not. Shown in the
    #: dashboard: a fallback the operator cannot see the reason for looks like
    #: the copilot simply never using a model.
    fallback_reason: str | None
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


def _describe(label: str) -> str:
    """A class label as a technician reads it, and its Sehwa code if it has one.

    A bare label such as MISALIGNMENT tells a model nothing about which part to
    check, and a small local model given only that falls back on listing every
    maintenance code in the table.
    """
    try:
        fault = FaultClass(label)
    except ValueError:
        return label
    ko, en, _, _ = FAULT_META[fault]
    code = FAULT_TO_ERR_CODE.get(fault)
    return f"{label} = {ko} ({en}); " + (f"Sehwa code {code}" if code else "no Sehwa maintenance code")


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
            f"Conformal prediction set at 90% coverage contains {len(ps)} labels, "
            "which the model cannot rule out:"
        )
        lines.extend(f"  - {_describe(label)}" for label in ps)
    elif ps:
        lines.append(f"Conformal prediction set contains only {_describe(ps[0])}.")
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


# -- Ollama -------------------------------------------------------------------
# Standard library only: the endpoint is two JSON calls, and a client library
# would be a dependency every clone installs for a feature that is optional.


class OllamaError(RuntimeError):
    pass


def _ollama(path: str, payload: dict | None, timeout: float) -> dict:
    url = settings.ollama_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # Ollama reports a missing model as a 404 with a JSON error body.
        try:
            detail = json.loads(exc.read().decode()).get("error", str(exc))
        except (ValueError, OSError):
            detail = str(exc)
        raise OllamaError(detail) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OllamaError(f"Ollama not reachable at {settings.ollama_url}") from exc


def installed_models(timeout: float = 2.0) -> list[dict[str, Any]]:
    """Models installed in the local Ollama that can write, smallest first.

    `/api/tags` is not quite a list of models. Newer Ollama lists a name once
    per runner that can serve it, and lists a runner's blob under an alias
    named after its digest; neither is something a person pulled. Embedding
    models are listed too and cannot draft anything. Raises OllamaError.
    """
    tags = _ollama("/api/tags", None, timeout)
    seen: set[str] = set()
    models = []
    for m in tags.get("models", []):
        name = m.get("name", "")
        caps = m.get("capabilities")
        if not name or name in seen:
            continue
        if caps is not None and "completion" not in caps:
            continue
        if m.get("digest") and name.split(":", 1)[-1] == m["digest"]:
            continue
        seen.add(name)
        models.append({"name": name, "size_gb": round(m.get("size", 0) / 1e9, 1)})
    return sorted(models, key=lambda m: (m["size_gb"], m["name"]))


def model_menu() -> dict[str, Any]:
    """What the dashboard may offer. Only free, local models are selectable."""
    if settings.copilot_provider == "claude":
        return {"provider": "claude", "default": settings.claude_model,
                "models": [], "unavailable": None if _has_credentials() else "no Claude API key"}
    try:
        models = installed_models()
    except OllamaError as exc:
        return {"provider": "ollama", "default": None, "models": [], "unavailable": str(exc)}
    names = [m["name"] for m in models]
    default = settings.ollama_model if settings.ollama_model in names else (names[0] if names else None)
    return {"provider": "ollama", "default": default, "models": models,
            "unavailable": None if names else "no models installed - run `ollama pull <model>`"}


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _draft_ollama(user_text: str, model: str) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        # A reasoning pass roughly doubles the wait on a CPU and is not shown
        # to the technician. Models that cannot think reject the flag, hence
        # the retry without it.
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 1200},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    try:
        out = _ollama("/api/chat", payload, settings.ollama_timeout_s)
    except OllamaError as exc:
        if "think" not in str(exc).lower():
            raise
        payload.pop("think")
        out = _ollama("/api/chat", payload, settings.ollama_timeout_s)
    # Some models still inline their reasoning; the technician gets the answer.
    text = _THINK.sub("", out.get("message", {}).get("content", "")).strip()
    if not text:
        raise OllamaError(f"{model} returned no text")
    return text


def _draft_claude(user_text: str) -> str:
    import anthropic

    response = anthropic.Anthropic().messages.create(
        model=settings.claude_model,
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
    return text


def answer(
    event: dict, machine: dict | None, question: str | None = None, model: str | None = None,
) -> CopilotReply:
    """Draft a work order, or answer a question about this event.

    ``model`` picks a local Ollama model and must already be validated against
    `installed_models()`; it is ignored for the Claude provider, whose model is
    the operator's to choose.
    """
    ctx = build_context(event, machine)
    citations = [ctx["err_code"]] if ctx["err_code"] else []

    def reply(text: str, source: str, used: str | None, reason: str | None) -> CopilotReply:
        return CopilotReply(answer=text, source=source, model=used, fallback_reason=reason,
                            grounded_on=ctx, citations=citations, disclaimer=DISCLAIMER_EN)

    def fallback(reason: str) -> CopilotReply:
        # An operations console must not lose a feature because a model call
        # failed. Fall back to the grounded draft, and say which path ran and why.
        print(f"[copilot] falling back to the deterministic draft: {reason}")
        return reply(_deterministic(ctx, question), "deterministic", None, reason)

    if not settings.copilot_enabled:
        return fallback("the language-model copilot is disabled")

    user_text = _context_block(ctx)
    user_text += (
        f"\n\nThe technician asks: {question}"
        if question
        else "\n\nDraft the work order for this event, in Korean and English."
    )

    if settings.copilot_provider == "claude":
        if not _has_credentials():
            return fallback("no Claude API key is configured")
        try:
            return reply(_draft_claude(user_text), "claude", settings.claude_model, None)
        except Exception as exc:  # noqa: BLE001 - any failure must still produce a draft
            return fallback(f"Claude call failed: {exc}")

    try:
        menu = model_menu() if model is None else None
        chosen = model or (menu["default"] if menu else None)
        if not chosen:
            return fallback((menu or {}).get("unavailable") or "no local model available")
        return reply(_draft_ollama(user_text, chosen), "ollama", chosen, None)
    except OllamaError as exc:
        return fallback(str(exc))
    except Exception as exc:  # noqa: BLE001 - any failure must still produce a draft
        return fallback(f"local model failed: {exc}")
