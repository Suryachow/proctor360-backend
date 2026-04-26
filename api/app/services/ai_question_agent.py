from __future__ import annotations

from app.core.config import settings
from urllib.parse import quote

from app.services.exam_generator import generate_mcq_set
from app.services.groq_exam_generator import generate_mcq_set_with_groq


def _is_reasoning_topic(topic: str) -> bool:
    topic_l = (topic or "").lower()
    markers = [
        "blood relation",
        "family relation",
        "relation puzzle",
        "logical reasoning",
        "verbal reasoning",
        "seating arrangement",
        "syllogism",
    ]
    return any(marker in topic_l for marker in markers)


def _build_reasoning_fallback_questions(topic: str, question_count: int, start_index: int = 0) -> list[dict]:
    names = ["Amit", "Bina", "Charan", "Divya", "Esha", "Farhan", "Gita", "Harsh", "Ira", "Jatin", "Kavya", "Lalit"]
    templates = [
        (
            "{a} is the brother of {b}. {b} is the mother of {c}. How is {a} related to {c}?",
            "Uncle",
            ["Father", "Brother", "Cousin"],
        ),
        (
            "{a} is the daughter of {b}. {b} is the son of {c}. How is {a} related to {c}?",
            "Granddaughter",
            ["Niece", "Daughter", "Sister"],
        ),
        (
            "{a} is the father of {b}. {b} is the sister of {c}. How is {a} related to {c}?",
            "Father",
            ["Uncle", "Brother", "Grandfather"],
        ),
        (
            "{a} is the wife of {b}. {b} is the brother of {c}. How is {a} related to {c}?",
            "Sister-in-law",
            ["Cousin", "Aunt", "Mother"],
        ),
        (
            "{a} is the son of {b}. {b} is the sister of {c}. How is {a} related to {c}?",
            "Nephew",
            ["Son", "Brother", "Uncle"],
        ),
        (
            "{a} is the mother of {b}. {b} is the father of {c}. How is {a} related to {c}?",
            "Grandmother",
            ["Mother", "Aunt", "Sister"],
        ),
    ]

    questions: list[dict] = []
    for i in range(start_index, start_index + question_count):
        t_prompt, t_correct, t_distractors = templates[i % len(templates)]
        a = names[i % len(names)]
        b = names[(i + 3) % len(names)]
        c = names[(i + 7) % len(names)]
        prompt = t_prompt.format(a=a, b=b, c=c)
        options = [t_correct, *t_distractors]
        shift = i % 4
        ordered = options[shift:] + options[:shift]
        correct_option = ["A", "B", "C", "D"][ordered.index(t_correct)]
        questions.append(
            {
                "prompt": prompt,
                "option_a": ordered[0],
                "option_b": ordered[1],
                "option_c": ordered[2],
                "option_d": ordered[3],
                "correct_option": correct_option,
                "topic": topic.lower(),
            }
        )

    return questions


def _build_fallback_questions(topic: str, difficulty: str, question_count: int, seed_offset: int) -> list[dict]:
    if _is_reasoning_topic(topic):
        return _build_reasoning_fallback_questions(topic, question_count, start_index=seed_offset)
    return generate_mcq_set(topic, difficulty, question_count, start_index=seed_offset)


def _prompt_key(prompt: str) -> str:
    return " ".join((prompt or "").strip().lower().split())


def _strip_visual_markers(prompt: str) -> str:
    lines = []
    for line in (prompt or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("[[IMAGE_URL]]"):
            continue
        if stripped.startswith("[[IMAGE_ALT]]"):
            continue
        if stripped.startswith("[[DIAGRAM_MERMAID]]"):
            continue
        if stripped.startswith("[[DIAGRAM_ALT]]"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _apply_visual_markers(
    questions: list[dict],
    topic: str,
    image_question_count: int,
    diagram_question_count: int,
) -> list[dict]:
    image_question_count = max(0, min(image_question_count, len(questions)))
    diagram_question_count = max(0, min(diagram_question_count, len(questions)))

    with_images = []
    for idx, q in enumerate(questions):
        prompt = _strip_visual_markers(str(q.get("prompt", "")).strip())
        if idx < image_question_count:
            label = quote(f"{topic} visual {idx + 1}")
            image_url = f"https://dummyimage.com/960x540/0f172a/e2e8f0.png&text={label}"
            prompt = f"{prompt}\n[[IMAGE_URL]]{image_url}\n[[IMAGE_ALT]]Reference visual for {topic} scenario {idx + 1}"

        if idx < diagram_question_count:
            diagram = "flowchart TD;A[Input]-->B[Process];B-->C[Validation];C-->D[Output]"
            prompt = f"{prompt}\n[[DIAGRAM_MERMAID]]{diagram}\n[[DIAGRAM_ALT]]Process flow diagram"

        with_images.append({**q, "prompt": prompt})

    return with_images


def _is_high_quality_prompt(prompt: str, topic: str) -> bool:
    text = " ".join((prompt or "").strip().lower().split())
    reasoning_topic = _is_reasoning_topic(topic)

    if len(text) < (45 if reasoning_topic else 90):
        return False

    generic_markers = [
        "what should they do first",
        "what is the first step",
        "which is true",
        "which is correct",
        "define ",
        "program ",
        "case ",
        "generic",
    ]
    if any(marker in text for marker in generic_markers):
        return False

    scenario_markers = [
        "team",
        "incident",
        "workflow",
        "shipment",
        "audit",
        "system",
        "client",
        "operator",
        "engineer",
        "manager",
        "minutes",
        "hours",
        "km",
        "%",
    ]
    reasoning_markers = [
        "father",
        "mother",
        "brother",
        "sister",
        "uncle",
        "aunt",
        "cousin",
        "grand",
        "relation",
        "family",
        "husband",
        "wife",
        "son",
        "daughter",
    ]
    if reasoning_topic:
        if not any(marker in text for marker in reasoning_markers):
            return False
    else:
        if not any(marker in text for marker in scenario_markers):
            return False

    quality_dimensions = 0
    if any(role in text for role in ["manager", "analyst", "engineer", "lead", "administrator", "operator", "coordinator"]):
        quality_dimensions += 1
    if any(constraint in text for constraint in ["deadline", "budget", "sla", "compliance", "risk", "outage", "capacity", "latency", "throughput"]):
        quality_dimensions += 1
    if any(goal in text for goal in ["must", "target", "objective", "reduce", "improve", "maintain", "achieve"]):
        quality_dimensions += 1
    if any(ch.isdigit() for ch in text):
        quality_dimensions += 1
    if not reasoning_topic and quality_dimensions < 2:
        return False

    topic_tokens = {token for token in topic.lower().split() if len(token) > 3}
    if topic_tokens and not any(token in text for token in topic_tokens):
        return False

    return True


def _is_high_quality_question(question: dict, topic: str) -> bool:
    prompt = str(question.get("prompt", ""))
    if not _is_high_quality_prompt(prompt, topic):
        return False

    options = [
        str(question.get("option_a", "")).strip(),
        str(question.get("option_b", "")).strip(),
        str(question.get("option_c", "")).strip(),
        str(question.get("option_d", "")).strip(),
    ]

    min_option_len = 3 if _is_reasoning_topic(topic) else 8
    if any(len(option) < min_option_len for option in options):
        return False
    if len(set(option.lower() for option in options)) < 4:
        return False

    trivial_options = {"100%", "50%", "20%", "0%"}
    if sum(1 for option in options if option in trivial_options) >= 2:
        return False

    return True


async def _collect_groq_candidates(
    topic: str,
    difficulty: str,
    question_count: int,
    image_question_count: int,
    diagram_question_count: int,
    admin_request: str | None,
) -> list[dict]:
    candidates: list[dict] = []

    target_pool_size = max(question_count * 2, question_count + 8)
    batch_count = min(10, max(5, question_count // 2))
    attempts = [
        f"{(admin_request or '').strip()} Focus on practical workplace decisions and numeric reasoning where relevant.",
        f"{(admin_request or '').strip()} Avoid theory-only prompts and include operational constraints in each scenario.",
        f"{(admin_request or '').strip()} Ensure each question has unique context and non-obvious distractors.",
        admin_request,
        "Generate high-quality topic-specific questions with diverse contexts.",
        "Generate clear, unambiguous expert-level MCQs with realistic reasoning requirements.",
    ]

    for attempt_index, request_hint in enumerate(attempts):
        try:
            batch = await generate_mcq_set_with_groq(
                topic=topic,
                difficulty=difficulty,
                question_count=batch_count,
                # Generate question text reliably first; visual markers are applied after selection.
                image_question_count=0,
                diagram_question_count=0,
                admin_request=f"{(request_hint or '').strip()} Batch {attempt_index + 1}",
            )
            candidates.extend(batch)
        except Exception:
            continue

        if len(candidates) >= target_pool_size:
            break

    return candidates


async def generate_questions_with_ai_agent(
    topic: str,
    difficulty: str,
    question_count: int,
    image_question_count: int,
    diagram_question_count: int,
    admin_request: str | None,
    existing_prompt_keys: set[str],
) -> list[dict]:
    if not (settings.groq_api_key or settings.groq_api_keys):
        raise ValueError("High-quality AI generation requires GROQ_API_KEY. Add it to .env and restart api service.")

    candidates = await _collect_groq_candidates(
        topic=topic,
        difficulty=difficulty,
        question_count=question_count,
        image_question_count=image_question_count,
        diagram_question_count=diagram_question_count,
        admin_request=admin_request,
    )
    if not candidates:
        seed_offset = len(existing_prompt_keys) % 101
        fallback = _build_fallback_questions(topic, difficulty, question_count, seed_offset)
        return _apply_visual_markers(fallback, topic, image_question_count, diagram_question_count)

    selected: list[dict] = []
    seen = set(existing_prompt_keys)
    selected_keys: set[str] = set()
    backup_pool: list[dict] = []

    for q in candidates:
        prompt = q.get("prompt", "")
        key = _prompt_key(prompt)
        if not key or key in seen:
            continue
        if _is_high_quality_question(q, topic):
            seen.add(key)
            selected_keys.add(key)
            selected.append(q)
            if len(selected) >= question_count:
                return _apply_visual_markers(selected, topic, image_question_count, diagram_question_count)
            continue

        # Keep non-duplicate candidates as backup when model output is partially weaker than desired.
        backup_pool.append(q)

    for q in backup_pool:
        prompt = q.get("prompt", "")
        key = _prompt_key(prompt)
        if not key or key in seen:
            continue
        seen.add(key)
        selected_keys.add(key)
        selected.append(q)
        if len(selected) >= question_count:
            return _apply_visual_markers(selected, topic, image_question_count, diagram_question_count)

    # If prior database overlap is too high, allow top-up with new batch items that are unique within this request.
    if len(selected) < question_count:
        for q in candidates:
            prompt = q.get("prompt", "")
            key = _prompt_key(prompt)
            if not key or key in selected_keys:
                continue
            selected_keys.add(key)
            selected.append(q)
            if len(selected) >= question_count:
                return _apply_visual_markers(selected, topic, image_question_count, diagram_question_count)

    raise ValueError("AI model did not return enough usable questions. Retry with a specific admin request.")
