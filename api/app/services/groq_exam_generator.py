import json
import re
from typing import Any

import httpx

from app.core.config import settings


_IMAGE_STEM = "https://dummyimage.com/960x540/0f172a/e2e8f0.png&text="
_GROQ_KEY_INDEX = 0


def _get_groq_keys() -> list[str]:
    keys = []
    for raw_key in (settings.groq_api_keys or "").split(","):
        key = raw_key.strip()
        if key:
            keys.append(key)

    fallback_key = (settings.groq_api_key or "").strip()
    if fallback_key and fallback_key not in keys:
        keys.append(fallback_key)

    return keys


def _next_groq_key(keys: list[str]) -> str:
    global _GROQ_KEY_INDEX

    if not keys:
        raise ValueError("GROQ_API_KEY is not configured")

    key = keys[_GROQ_KEY_INDEX % len(keys)]
    _GROQ_KEY_INDEX = (_GROQ_KEY_INDEX + 1) % len(keys)
    return key


def _is_reasoning_topic(topic: str) -> bool:
    topic_l = (topic or "").lower()
    reasoning_markers = [
        "blood relation",
        "family relation",
        "relation puzzle",
        "logical reasoning",
        "verbal reasoning",
        "seating arrangement",
        "syllogism",
    ]
    return any(marker in topic_l for marker in reasoning_markers)


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty model response")

    # Attempt direct JSON parse first.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback for markdown fenced responses.
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
    if not match:
        raise ValueError("Model did not return valid JSON")

    parsed = json.loads(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError("Invalid JSON object shape")
    return parsed


def _normalize_question(item: dict[str, Any], topic: str, idx: int) -> dict[str, Any]:
    prompt = str(item.get("prompt", "")).strip()
    option_a = str(item.get("option_a", "")).strip()
    option_b = str(item.get("option_b", "")).strip()
    option_c = str(item.get("option_c", "")).strip()
    option_d = str(item.get("option_d", "")).strip()
    correct_option = str(item.get("correct_option", "")).strip().upper()

    if not prompt or not option_a or not option_b or not option_c or not option_d:
        raise ValueError(f"Question #{idx + 1} has missing fields")

    if correct_option not in {"A", "B", "C", "D"}:
        raise ValueError(f"Question #{idx + 1} has invalid correct option")

    image_url = str(item.get("image_url", "")).strip()
    image_alt = str(item.get("image_alt", "")).strip()
    if image_url:
        alt = image_alt or f"Illustration for {topic} question {idx + 1}"
        prompt = f"{prompt}\n[[IMAGE_URL]]{image_url}\n[[IMAGE_ALT]]{alt}"

    diagram_mermaid = str(item.get("diagram_mermaid", "")).strip()
    diagram_alt = str(item.get("diagram_alt", "")).strip()
    if diagram_mermaid:
        alt = diagram_alt or f"Diagram for {topic} question {idx + 1}"
        prompt = f"{prompt}\n[[DIAGRAM_MERMAID]]{diagram_mermaid}\n[[DIAGRAM_ALT]]{alt}"

    return {
        "prompt": prompt,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "correct_option": correct_option,
        "topic": str(item.get("topic", topic)).strip().lower() or topic.lower(),
    }


def _prompt_key(prompt: str) -> str:
    return " ".join((prompt or "").strip().lower().split())


async def generate_mcq_set_with_groq(
    topic: str,
    difficulty: str,
    question_count: int,
    image_question_count: int,
    diagram_question_count: int,
    admin_request: str | None,
) -> list[dict[str, Any]]:
    groq_keys = _get_groq_keys()
    if not groq_keys:
        raise ValueError("GROQ_API_KEY is not configured")

    image_question_count = max(0, min(image_question_count, question_count))
    diagram_question_count = max(0, min(diagram_question_count, question_count))

    admin_context = (admin_request or "").strip()
    if not admin_context:
        admin_context = "none provided"

    reasoning_topic = _is_reasoning_topic(topic)

    system_prompt = (
        "You are an expert exam setter for professional certification-style assessments. "
        "Return strict JSON only. Generate realistic, scenario-based MCQ questions with one correct option each. "
        "Avoid textbook-definition or rote-memory questions."
    )

    style_clause = (
        "Every question must be practical and real-world (workplace, operations, troubleshooting, decision-making, or case-study style), "
        "not abstract textbook definitions. "
        "Each prompt must include: role/persona, operating context, explicit constraint, and decision objective. "
        "All options must be plausible and close in quality; avoid obviously wrong distractors. "
        "Do NOT ask generic wording such as 'what is the first step', 'which is true', or basic definition checks. "
        "Do NOT use trivial option sets like 0/20/50/100 unless mathematically derived from the scenario. "
    )
    if reasoning_topic:
        style_clause = (
            "Generate high-quality reasoning puzzles relevant to the topic. "
            "For blood/family relation topics, use clear family-tree or statement-based logic setups with unambiguous relationships. "
            "Avoid vague wording and avoid trivial definition-only prompts. "
            "All options must be plausible and require logical reasoning, not guesswork. "
        )

    user_prompt = (
        f"Generate {question_count} multiple-choice questions for topic '{topic}' at {difficulty} level. "
        f"Exactly {image_question_count} questions must include an image_url and image_alt field. "
        f"Exactly {diagram_question_count} questions must include diagram_mermaid and diagram_alt fields. "
        f"{style_clause}"
        "Do not repeat prompts, rephrase the same scenario, or reuse the same answer pattern across questions. "
        f"Admin request context: {admin_context}. "
        "Use stable placeholder image URLs by appending encoded short text to this base: "
        f"{_IMAGE_STEM}. "
        "Output format must be: {\"questions\": ["
        "{\"prompt\":\"...\",\"option_a\":\"...\",\"option_b\":\"...\",\"option_c\":\"...\",\"option_d\":\"...\",\"correct_option\":\"A|B|C|D\",\"topic\":\"...\",\"image_url\":\"...\",\"image_alt\":\"...\",\"diagram_mermaid\":\"...\",\"diagram_alt\":\"...\"}"
        "]}. Non-image questions must omit image_url/image_alt. Non-diagram questions must omit diagram_mermaid/diagram_alt."
    )

    last_error: Exception | None = None
    payload = None
    async with httpx.AsyncClient(timeout=45.0) as client:
        for _ in range(len(groq_keys)):
            api_key = _next_groq_key(groq_keys)
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": settings.groq_model,
                        "temperature": 0.7,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:
                last_error = exc
                continue

    if payload is None:
        raise ValueError(f"Groq request failed across all configured keys: {last_error}")

    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)

    questions = parsed.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("Groq response does not include questions list")

    normalized: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for idx, item in enumerate(questions):
        if not isinstance(item, dict):
            raise ValueError("Groq question item must be an object")
        normalized_question = _normalize_question(item, topic, idx)
        key = _prompt_key(normalized_question["prompt"])
        if key in seen_prompts:
            continue
        seen_prompts.add(key)
        normalized.append(normalized_question)
        if len(normalized) >= max(question_count * 2, question_count + 6):
            break

    if len(normalized) < min(3, question_count):
        raise ValueError("Groq returned too few usable questions")

    return normalized
