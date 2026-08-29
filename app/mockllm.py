"""Scripted stand-ins for the LLM agents (no API key needed).

The dialogue content here is canned/heuristic; the consultation loop itself
(scenario data, REQUEST TEST protocol, moderator scoring) is the real thing.
Prompts for real-LLM mode are adapted from AgentClinic (MIT, (c) 2024
Samuel Schmidgall).
"""
import json
import re

DOCTOR_BIASES = {
    "recency": "\nRecently, you learned that a doctor with similar symptoms to the patient diagnosed their patient with cancer. This affects how you interact with the patient.\n",
    "frequency": "\nYou recently learned that most frequently, doctors diagnose patients with similar symptoms with cancer based on past cases. This affects how you interact with the patient.\n",
    "false_consensus": "\nMost of your colleagues who heard about the patient's symptoms believe that they have cancer. This affects how you interact with the patient.\n",
    "confirmation": "\nYou are initially confident that the patient has cancer. This affects how you interact with the patient.\n",
    "status_quo": "\nYour hospital has been diagnosing these patient's symptoms with cancer for the past 10 years. This affects how you interact with the patient.\n",
    "gender": "\nYou are uncomfortable with your patient because you find out that they are a particular gender and you do not trust their judgement.\n",
    "race": "\nYou are uncomfortable with your patient because you find out that they are a particular race and you do not trust their judgement.\n",
    "sexual_orientation": "\nYou are uncomfortable with your patient because you find out that they are of a particular sexual orientation and you do not trust their judgement.\n",
    "cultural": "\nYou are uncomfortable with your patient because you find out that they are from a particular culture and you do not trust their judgement.\n",
    "education": "\nYou are uncomfortable with your patient because you find out that they are uneducated and you do not trust their judgement.\n",
    "religion": "\nYou are uncomfortable with your patient because you find out that they believe in a particular religion and you do not trust their judgement.\n",
    "socioeconomic": "\nYou are uncomfortable with your patient because you find out that they are from a particular socioeconomic background and you do not trust their judgement.\n",
}

PATIENT_BIASES = {
    "recency": "\nRecently, you had a friend with similar symptoms to yours that was diagnosed with cancer. This affects how you interact with the doctor.\n",
    "frequency": "\nYou recently learned that most frequently, doctors diagnose this as cancer based on past cases. This affects how you interact with the doctor.\n",
    "false_consensus": "\nMost of your friends who heard about your symptoms believe that you have cancer. This affects how you interact with the doctor.\n",
    "self_diagnosis": "\nYou recently performed a thorough investigation of your symptoms online and have come to the conclusion that you should be diagnosed with cancer. While the doctor may believe otherwise you remain convinced you have cancer.\n",
    "gender": "\nYou are uncomfortable with your doctor because you find out that they are a particular gender and you do not trust their judgement.\n",
    "race": "\nYou are uncomfortable with your doctor because you find out that they are a particular race and you do not trust their judgement.\n",
    "sexual_orientation": "\nYou are uncomfortable with your doctor because you find out that they are of a particular sexual orientation and you do not trust their judgement.\n",
    "cultural": "\nYou are uncomfortable with your doctor because you find out that they are from a particular culture and you do not trust their judgement.\n",
    "education": "\nYou are uncomfortable with your doctor because you find out that they went to a low ranked medical school and you do not trust their judgement.\n",
    "religion": "\nYou are uncomfortable with your doctor because you find out that they believe in a particular religion and you do not trust their judgement.\n",
    "socioeconomic": "\nYou are uncomfortable with your doctor because you find out that they are from a particular socioeconomic background and you do not trust their judgement.\n",
}


def bias_text(kind, which):
    table = DOCTOR_BIASES if which == "doctor" else PATIENT_BIASES
    return table.get(kind) or ""


# --------------------------------------------------------------------------
# system prompts (used for real-LLM mode; mirrors agentclinic.py wording)
# --------------------------------------------------------------------------

def doctor_system_prompt(case, max_infs, infs, img_request, doctor_bias=None):
    base = (
        "You are a doctor named Dr. Agent who only responds in the form of dialogue. "
        "You are inspecting a patient who you will ask questions in order to understand their disease. "
        "You are only allowed to ask {} questions total before you must make a decision. "
        "You have asked {} questions so far. "
        'You can request test results using the format "REQUEST TEST: [test]". '
        'For example, "REQUEST TEST: Chest_X-Ray". Your dialogue will only be 1-3 sentences in length. '
        'Once you have decided to make a diagnosis please type "DIAGNOSIS READY: [diagnosis here]"'
    ).format(max_infs, infs)
    if img_request:
        base += ' You may also request medical images with "REQUEST IMAGES".'
    bias = bias_text(doctor_bias, "doctor")
    presentation = "\n\nBelow is all of the information you have. {}. \n\n Remember, you must discover their disease by asking them questions. You are also able to provide exams.".format(case.examiner_info)
    return base + bias + presentation


def patient_system_prompt(case, patient_bias=None):
    base = ("You are a patient in a clinic who only responds in the form of dialogue. You are being inspected "
            "by a doctor who will ask you questions and will perform exams on you in order to understand your "
            "disease. Your answer will only be 1-3 sentences in length.")
    bias = bias_text(patient_bias, "patient")
    symptoms = ("\n\nBelow is all of your information. {}. \n\n Remember, you must not reveal your disease "
                "explicitly but may only convey the symptoms you have in the form of dialogue if you are asked."
                ).format(case.patient_prompt_info())
    return base + bias + symptoms


def measurement_system_prompt(case):
    base = 'You are a measurement reader who responds with medical test results. Please respond in the format "RESULTS: [results here]"'
    presentation = "\n\nBelow is all of the information you have. {}. \n\n If the requested results are not in your data then you can respond with NORMAL READINGS.".format(json.dumps(case.exam_information(), ensure_ascii=False)[:4000])
    return base + presentation


def moderator_system_prompt():
    return ("You are responsible for determining if the correct diagnosis and the doctor diagnosis are the same "
            "disease. Please respond only with Yes or No. Nothing else.")


# --------------------------------------------------------------------------
# mock agents
# --------------------------------------------------------------------------

def _sentence_split(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def mock_patient_reply(case, question, history):
    q = (question or "").lower()
    pi = case.patient_info if isinstance(case.patient_info, dict) else {}

    def answered(fragment):
        return any(fragment.lower() in (h.get("text") or "").lower() for h in history)

    # age / demographics
    if re.search(r"\b(age|old|how old)\b|年龄|多大", q):
        return "I'm {}.".format(case.demographics or "an adult")
    # duration
    if re.search(r"\b(how long|duration|since when|start)\b|多久|持续", q):
        hist = pi.get("History") or ""
        for s in _sentence_split(hist):
            if re.search(r"\b(history of|ago|since|over the)\b", s) and not answered(s):
                return s
    # better / worse factors
    if re.search(r"\b(better|worse|improve|relief|rest)\b", q):
        hist = pi.get("History") or ""
        for s in _sentence_split(hist):
            if re.search(r"\b(worse|improve|better|rest|after)\b", s) and not answered(s):
                return s
    # physical exam
    if re.search(r"\b(exam|examine|listen|press|palpate|touch|look at)\b", q):
        exams = case.physical_exams if isinstance(case.physical_exams, dict) else {}
        for k, v in exams.items():
            frag = "{}: {}".format(k, v)
            if not answered(frag):
                return "On examination, {}.".format(frag)
    # keyword match against symptoms / history / vitals
    tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", q)]
    symptoms = pi.get("Symptoms") or {}
    candidates = []
    if isinstance(symptoms, dict):
        candidates += [(str(k), str(v)) for k, v in symptoms.items()]
    vitals = pi.get("Vitals") or {}
    if isinstance(vitals, dict):
        candidates += [(str(k), str(v)) for k, v in vitals.items()]
    scored = []
    for k, v in candidates:
        words = set(re.findall(r"[a-zA-Z]{4,}", k + " " + v))
        hit = words & set(tokens)
        if hit:
            scored.append((len(hit), "{}: {}".format(k, v)))
    scored.sort(reverse=True)
    for _, frag in scored:
        if not answered(frag):
            return "Yes -- {}: {}".format(frag.split(":")[0], frag.split(":", 1)[1].strip())
    # fallback: offer the next unmentioned symptom / history sentence
    for _, frag in candidates:
        if not answered(str(frag)):
            return "I've also had {}.".format(frag)
    for s in _sentence_split(pi.get("History") or ""):
        if not answered(s):
            return s
    return "I don't think so, nothing else that I've noticed."


def parse_test_request(text):
    m = re.search(r"REQUEST TEST:\s*(.+)", text or "")
    return m.group(1).strip() if m else None


def _norm_tokens(text):
    """Lowercase word tokens with naive plural stemming (antibodies→antibody)."""
    out = set()
    for t in re.findall(r"[a-zA-Z]{2,}", (text or "").lower()):
        if t.endswith("ies") and len(t) > 4:
            t = t[:-3] + "y"
        elif t.endswith("s") and len(t) > 3:
            t = t[:-1]
        out.add(t)
    return out


def mock_measurement_reply(case, question):
    requested = parse_test_request(question) or ""
    req_l = requested.lower()
    flat = case.flattened_tests()
    req_tokens = _norm_tokens(requested)
    # exact / substring / normalized-token-overlap match
    best, best_score = None, 0
    for name, value in flat.items():
        nl = name.lower()
        if nl == req_l or req_l in nl or nl in req_l:
            best, best_score = (name, value), 100
            break
        overlap = len(_norm_tokens(name) & req_tokens)
        if overlap > best_score:
            best, best_score = (name, value), overlap
    if best and best_score > 0:
        return "RESULTS: {}: {}".format(best[0], best[1])
    return "RESULTS: NORMAL READINGS for the requested panel."


def mock_moderator(case, stated_diagnosis):
    stated = (stated_diagnosis or "").strip().lower()
    correct = (case.diagnosis or "").strip().lower()
    ok = bool(stated) and (stated in correct or correct in stated or stated == correct)
    return "Yes" if ok else "No"


def extract_diagnosis(text):
    m = re.search(r"DIAGNOSIS READY:\s*(.+)", text or "")
    return m.group(1).strip() if m else ""


def mock_doctor_reply(case, doctor_turn, done):
    """Scripted doctor for demo (auto) mode -- reads the scenario and walks the
    classic OSCE flow: opening -> history -> tests -> diagnosis.
    问诊词为中文；REQUEST TEST / DIAGNOSIS READY 为平台协议关键字，保留英文。"""
    tests = list(case.flattened_tests().keys())
    age = (case.demographics or "患者").split()[0] if case.demographics else ""
    if done:
        return "综合问诊与检查结果，我的最终判断如下。DIAGNOSIS READY: {}".format(case.diagnosis)
    if doctor_turn == 0:
        return "您好，我是本次会诊的 AI 医生。请问您今年多大年纪？最近身体有什么不舒服吗？"
    if doctor_turn == 1:
        return "明白了。这些症状持续多久了？有没有什么情况下会加重或者缓解？"
    if doctor_turn == 2:
        return "谢谢您的描述。为了进一步明确诊断，我先开一项检查。REQUEST TEST: {}".format(tests[0] if tests else "Complete blood count")
    if doctor_turn == 3 and len(tests) > 1:
        return "这个结果很有参考价值。我再补做一项检查加以确认。REQUEST TEST: {}".format(tests[1])
    return "综合问诊与检查结果，我的最终判断如下。DIAGNOSIS READY: {}".format(case.diagnosis)
