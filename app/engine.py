"""Consultation engine: pure functions over (case, history) -> next event.

The web client drives the loop step by step, sending the full history each
time, which keeps the server stateless and restart-safe.

Event types returned:
  {type: "doctor"|"patient"|"measurement", role, text}
  {type: "verdict", correct, correct_answer, doctor_diagnosis}
  {type: "done"}

LLM settings support a separate model per agent role (the point of a
multi-agent platform): doctor_model / patient_model / measurement_model /
moderator_model, falling back to a shared `model`.
"""
from . import cases as cases_mod
from . import config as app_config
from . import mockllm
from . import llm

MAX_STEPS = 60


def _history_text(history):
    out = []
    for h in history:
        role = h.get("role")
        text = (h.get("text") or "").replace("\n", " ")
        out.append("{}: {}".format(role.capitalize(), text))
    return "\n".join(out)


def _llm_cfg(settings):
    """Normalize LLM settings from the request body (None in mock mode).

    服务端 config.json 提供默认 key/base_url/model，前端留空即用默认。
    """
    s = settings or {}
    if s.get("mode") != "llm":
        return None
    d = app_config.llm_defaults()
    api_key = (s.get("api_key") or "").strip() or d.get("api_key")
    if not api_key:
        return None
    default_model = (s.get("model") or "").strip() or d.get("model") or "gpt-4o-mini"
    base_url = (s.get("base_url") or "").strip() or d.get("base_url")
    return {
        "doctor_model": (s.get("doctor_model") or "").strip() or default_model,
        "patient_model": (s.get("patient_model") or "").strip() or default_model,
        "measurement_model": (s.get("measurement_model") or "").strip() or default_model,
        "moderator_model": (s.get("moderator_model") or "").strip() or default_model,
        # 角色系统提示词覆盖（留空 = 平台默认）
        "doctor_prompt": (s.get("doctor_prompt") or "").strip() or None,
        "patient_prompt": (s.get("patient_prompt") or "").strip() or None,
        "measurement_prompt": (s.get("measurement_prompt") or "").strip() or None,
        "moderator_prompt": (s.get("moderator_prompt") or "").strip() or None,
        "api_key": api_key,
        "base_url": base_url,
        "doctor_bias": s.get("doctor_bias") or None,
        "patient_bias": s.get("patient_bias") or None,
        "temperature": float(s.get("temperature") or 0.05),
        "max_tokens": int(s.get("max_tokens") or 400),
        "timeout": float(s.get("request_timeout") or 120),
    }


def _real_reply(cfg, role, system_prompt, user_prompt):
    """role: doctor | patient | measurement | moderator"""
    return llm.chat(
        cfg["{}_model".format(role)],
        system_prompt, user_prompt, cfg["api_key"], cfg["base_url"],
        max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
        timeout=cfg.get("timeout", 120))


# ---------------------------------------------------------------------------
# auto mode (AI doctor): one step from the current history
# ---------------------------------------------------------------------------

def auto_step(dataset, case_id, history, settings=None):
    case = cases_mod.get_case(dataset, case_id)
    cfg = _llm_cfg(settings)
    total_infs = int((settings or {}).get("total_inferences") or 10)
    history = list(history or [])

    if len(history) >= MAX_STEPS:
        return {"type": "done"}

    doctor_turns = [h for h in history if h.get("role") == "doctor"]
    turn = len(doctor_turns)

    if not history:
        text = mock_doctor(case, cfg, 0, total_infs, history=history)
        return {"type": "doctor", "role": "doctor", "text": text, "turn": 1, "total": total_infs}

    last = history[-1]

    if last.get("role") == "doctor":
        if "DIAGNOSIS READY" in last.get("text", ""):
            stated = mockllm.extract_diagnosis(last["text"])
            return judge(dataset, case_id, stated, settings)
        if "REQUEST TEST" in last.get("text", ""):
            text = mock_measurement(case, cfg, last["text"], history)
            return {"type": "measurement", "role": "measurement", "text": text}
        text = mock_patient(case, cfg, last["text"], history)
        return {"type": "patient", "role": "patient", "text": text}

    # otherwise it's the doctor's turn
    if turn >= total_infs:
        text = mock_doctor(case, cfg, turn, total_infs, force_final=True, history=history)
    else:
        text = mock_doctor(case, cfg, turn, total_infs, history=history)
    return {"type": "doctor", "role": "doctor", "text": text, "turn": turn + 1, "total": total_infs}


def mock_doctor(case, cfg, turn, total_infs, force_final=False, history=None):
    if cfg:
        system = cfg.get("doctor_prompt") or mockllm.doctor_system_prompt(
            case, total_infs, turn, False, cfg.get("doctor_bias"))
        hist = _history_text(history or [])
        last = (history or [{}])[-1]
        user = ("\nHere is a history of your dialogue: {hist}\n Here was the patient response: {last}\n"
                "Now please continue your dialogue\nDoctor: ").format(hist=hist, last=last.get("text", ""))
        return _real_reply(cfg, "doctor", system, user)
    return mockllm.mock_doctor_reply(case, turn, force_final)


def mock_patient(case, cfg, question, history):
    if cfg:
        system = cfg.get("patient_prompt") or mockllm.patient_system_prompt(case, cfg.get("patient_bias"))
        user = ("\nHere is a history of your dialogue: {hist}\n Here was the doctor response: {q}\n"
                "Now please continue your dialogue\nPatient: ").format(hist=_history_text(history), q=question)
        return _real_reply(cfg, "patient", system, user)
    return mockllm.mock_patient_reply(case, question, history)


def mock_measurement(case, cfg, question, history=None):
    if cfg:
        system = cfg.get("measurement_prompt") or mockllm.measurement_system_prompt(case)
        user = "\n Here was the doctor measurement request: {}".format(question)
        return _real_reply(cfg, "measurement", system, user)
    return mockllm.mock_measurement_reply(case, question)


# ---------------------------------------------------------------------------
# interactive mode (human doctor)
# ---------------------------------------------------------------------------

def ask(dataset, case_id, question, history, settings=None):
    """Route the human doctor's line: test order or patient question."""
    case = cases_mod.get_case(dataset, case_id)
    cfg = _llm_cfg(settings)
    if "REQUEST TEST" in (question or ""):
        text = mock_measurement(case, cfg, question, history)
        return {"type": "measurement", "role": "measurement", "text": text}
    if "DIAGNOSIS READY" in (question or ""):
        stated = mockllm.extract_diagnosis(question)
        return judge(dataset, case_id, stated, settings)
    text = mock_patient(case, cfg, question, history)
    return {"type": "patient", "role": "patient", "text": text}


def judge(dataset, case_id, stated_diagnosis, settings=None):
    case = cases_mod.get_case(dataset, case_id)
    cfg = _llm_cfg(settings)
    if cfg:
        user = ("\nHere is the correct diagnosis: {c}\n Here was the doctor dialogue: DIAGNOSIS READY: {d}\n"
                "Are these the same?").format(c=case.diagnosis, d=stated_diagnosis)
        system = cfg.get("moderator_prompt") or mockllm.moderator_system_prompt()
        try:
            answer = _real_reply(cfg, "moderator", system, user).lower()
            correct = answer.startswith("yes")
        except Exception:
            correct = None
        if correct is not None:
            return {"type": "verdict", "role": "moderator", "correct": correct,
                    "correct_answer": case.diagnosis, "doctor_diagnosis": stated_diagnosis}
    correct = mockllm.mock_moderator(case, stated_diagnosis) == "Yes"
    return {"type": "verdict", "role": "moderator", "correct": correct,
            "correct_answer": case.diagnosis, "doctor_diagnosis": stated_diagnosis}
