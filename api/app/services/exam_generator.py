import random
from typing import Any


_OPTION_KEYS = ["A", "B", "C", "D"]


def _build_mcq(topic: str, prompt: str, correct: str, distractors: list[str]) -> dict[str, Any]:
    choices = [correct, *distractors[:3]]
    random.shuffle(choices)
    correct_index = choices.index(correct)

    return {
        "prompt": prompt,
        "option_a": choices[0],
        "option_b": choices[1],
        "option_c": choices[2],
        "option_d": choices[3],
        "correct_option": _OPTION_KEYS[correct_index],
        "topic": topic.lower(),
    }


def _build_mcq_rotating(topic: str, prompt: str, correct: str, distractors: list[str], index: int) -> dict[str, Any]:
    choices = [correct, *distractors[:3]]
    shift = index % 4
    ordered = choices[shift:] + choices[:shift]
    correct_index = ordered.index(correct)

    return {
        "prompt": prompt,
        "option_a": ordered[0],
        "option_b": ordered[1],
        "option_c": ordered[2],
        "option_d": ordered[3],
        "correct_option": _OPTION_KEYS[correct_index],
        "topic": topic.lower(),
    }


def _algebra_easy(topic: str, index: int) -> dict[str, Any]:
    coefficient = (index % 5) + 2
    solution = (index % 8) + 2
    offset = (index * 3 % 9) + 1
    constant = coefficient * solution + offset

    prompt = f"Solve for x: {coefficient}x + {offset} = {constant}"
    correct = str(solution)
    distractors = [str(solution + 1), str(max(1, solution - 1)), str(solution + 2)]
    return _build_mcq(topic, prompt, correct, distractors)


def _algebra_medium(topic: str, index: int) -> dict[str, Any]:
    if index % 2 == 0:
        x = (index % 6) + 2
        y = (index % 5) + 1
        left = 2 * x + 3 * y
        right = x - y

        prompt = (
            "Given the system 2x + 3y = "
            f"{left} and x - y = {right}, what is the value of x?"
        )
        correct = str(x)
        distractors = [str(y), str(x + 1), str(max(1, x - 1))]
        return _build_mcq(topic, prompt, correct, distractors)

    a = (index % 4) + 2
    b = (index % 3) + 1
    constant = 3 * a + 4 * b
    prompt = f"Simplify: 3(2x - {a}) - 4(x + {b})"
    correct = f"2x - {constant}"
    distractors = [f"2x + {constant}", f"x - {constant}", f"6x - {constant}"]
    return _build_mcq(topic, prompt, correct, distractors)


def _algebra_hard(topic: str, index: int) -> dict[str, Any]:
    if index % 2 == 1:
        x_value = (index % 6) + 2
        numerator = (x_value + 1) * (x_value - 1)
        denominator = x_value - 1
        prompt = f"Evaluate the expression (x^2 - 1)/(x - 1) for x = {x_value}"
        correct = str(numerator // denominator)
        distractors = [str(x_value), str(x_value - 1), str(x_value + 2)]
        return _build_mcq(topic, prompt, correct, distractors)

    root_one = (index % 5) + 2
    root_two = (index % 4) + 6
    root_sum = root_one + root_two
    root_product = root_one * root_two

    prompt = (
        "If x^2 - "
        f"{root_sum}x + {root_product} = 0, what is the larger root?"
    )
    correct = str(max(root_one, root_two))
    distractors = [str(min(root_one, root_two)), str(root_sum), str(root_product)]
    return _build_mcq(topic, prompt, correct, distractors)


def _generic_easy(topic: str, index: int) -> dict[str, Any]:
    environments = ["logistics hub", "hospital operations desk", "retail distribution center", "IT service desk", "airport ground team", "manufacturing line"]
    roles = ["supervisor", "operations analyst", "team lead", "quality engineer", "dispatch coordinator", "process manager"]
    pain_points = ["missed SLAs", "routing delays", "handoff errors", "quality deviations", "resource overuse", "customer escalations"]

    environment = environments[index % len(environments)]
    role = roles[(index + 2) % len(roles)]
    pain = pain_points[(index + 4) % len(pain_points)]
    case_id = 300 + index

    prompt = (
        f"Case {case_id}: In a {environment}, a {role} is introducing a {topic.title()} workflow after recurring {pain}. "
        "What is the best first action to ensure a reliable rollout?"
    )
    correct = "Define baseline metrics, constraints, and success criteria, then run a controlled pilot"
    distractors = [
        "Deploy immediately across all teams and measure outcomes later",
        "Skip baseline analysis and rely only on stakeholder opinions",
        "Optimize speed first and postpone validation until post-launch",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def _generic_medium(topic: str, index: int) -> dict[str, Any]:
    if index % 2 == 1:
        backlog_items = 60 + ((index * 11) % 140)
        analysts = 3 + (index % 5)
        per_hour_old = 4 + (index % 4)
        per_hour_new = per_hour_old + 2 + (index % 3)

        old_capacity = analysts * per_hour_old
        new_capacity = analysts * per_hour_new
        gain = round(((new_capacity - old_capacity) / old_capacity) * 100)

        prompt = (
            f"An operations team uses {topic.title()} controls to process a backlog of {backlog_items} items. "
            f"Each of {analysts} analysts improved throughput from {per_hour_old} to {per_hour_new} items/hour. "
            "What is the percentage increase in team hourly capacity?"
        )
        correct = f"{gain}%"
        distractors = [
            f"{max(1, gain - 10)}%",
            f"{min(99, gain + 10)}%",
            f"{per_hour_new * 10}%",
        ]
        return _build_mcq_rotating(topic, prompt, correct, distractors, index)

    baseline_cycle_minutes = 28 + ((index * 3) % 36)
    improved_cycle_minutes = max(8, baseline_cycle_minutes - (4 + (index % 8)))
    daily_jobs = 140 + ((index * 13) % 220)

    baseline_total = baseline_cycle_minutes * daily_jobs
    improved_total = improved_cycle_minutes * daily_jobs
    reduction_percent = round(((baseline_total - improved_total) / baseline_total) * 100)

    prompt = (
        f"A team handling {daily_jobs} daily tasks redesigned its {topic.title()} process. "
        f"Average cycle time dropped from {baseline_cycle_minutes} minutes to {improved_cycle_minutes} minutes per task. "
        "What is the closest daily time reduction percentage?"
    )
    correct = f"{reduction_percent}%"
    distractors = [
        f"{min(99, reduction_percent + 12)}%",
        f"{max(1, reduction_percent - 12)}%",
        f"{max(1, round((improved_cycle_minutes / baseline_cycle_minutes) * 100))}%",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def _generic_hard(topic: str, index: int) -> dict[str, Any]:
    if index % 3 == 1:
        prompt = (
            f"A regulated enterprise is redesigning its {topic.title()} operating model across three regions. "
            "Regional teams demand custom workflows, but audit expects a common control baseline. "
            "Which approach best reduces compliance risk while preserving local agility?"
        )
        correct = "Define non-negotiable global controls, then allow region-specific extensions behind approval gates"
        distractors = [
            "Allow each region to define controls independently and reconcile findings at year-end",
            "Force one global workflow with no local adaptation regardless of legal requirements",
            "Delay control decisions until all teams complete implementation",
        ]
        return _build_mcq_rotating(topic, prompt, correct, distractors, index)

    if index % 3 == 2:
        incidents = 120 + ((index * 9) % 160)
        preventable = 35 + ((index * 5) % 30)
        alert_noise = 22 + ((index * 3) % 24)
        prompt = (
            f"Quarterly review of a {topic.title()} program shows {incidents} incidents, with {preventable}% marked preventable "
            f"and alert noise at {alert_noise}%. Leadership wants faster response without increasing false positives. "
            "Which strategy is most effective?"
        )
        correct = "Prioritize high-confidence signals, tune noisy rules with feedback loops, and track precision/recall weekly"
        distractors = [
            "Increase alert thresholds globally so teams receive fewer alerts regardless of severity",
            "Escalate every alert as critical to guarantee no incident is missed",
            "Add parallel tools without consolidating detection logic or metrics",
        ]
        return _build_mcq_rotating(topic, prompt, correct, distractors, index)

    contexts = ["incident response", "platform migration", "multi-site rollout", "audit remediation", "operations stabilization"]
    constraints = ["tight deadline", "limited budget", "strict compliance controls", "legacy integration risk", "small cross-functional team"]
    team_size = 4 + (index % 5)
    target = 96 + (index % 4)

    context = contexts[index % len(contexts)]
    constraint = constraints[(index + 1) % len(constraints)]

    prompt = (
        f"Program {index + 1}: During {context} for a {topic.title()} system under {constraint}, "
        f"a team of {team_size} must achieve {target}% reliability in one release cycle. "
        "Which plan best balances risk, speed, and control?"
    )
    correct = "Run a staged rollout with rollback thresholds, risk-based test coverage, and monitored checkpoints"
    distractors = [
        "Launch to all users at once and tune issues after production impact",
        "Focus only on throughput targets and defer quality controls",
        "Add multiple unvalidated tools to increase perceived coverage",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def _is_algebra_topic(topic: str) -> bool:
    topic_lower = topic.lower()
    return "algebra" in topic_lower or topic_lower in {"math", "mathematics"}


def is_time_speed_distance_topic(topic: str) -> bool:
    normalized = "".join(ch if ch.isalnum() else " " for ch in (topic or "").lower())
    tokens = {t for t in normalized.split() if t}
    has_time = "time" in tokens
    has_travel = "travel" in tokens
    has_distance = "distance" in tokens
    has_speed = "speed" in tokens
    return (has_time and has_travel and has_distance) or (has_time and has_speed and has_distance)


def _time_speed_distance_easy(topic: str, index: int) -> dict[str, Any]:
    distance = 90 + ((index * 15) % 260)
    speed = 30 + ((index * 10) % 55)
    hours = round(distance / speed, 2)

    prompt = (
        f"A delivery van must travel {distance} km at a constant speed of {speed} km/h to reach a warehouse. "
        "How long will the trip take (in hours)?"
    )
    correct = f"{hours} hours"
    distractors = [
        f"{round(hours + 0.5, 2)} hours",
        f"{round(max(0.25, hours - 0.5), 2)} hours",
        f"{round(distance * speed, 2)} hours",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def _time_speed_distance_medium(topic: str, index: int) -> dict[str, Any]:
    leg1_distance = 80 + ((index * 12) % 140)
    leg2_distance = 60 + ((index * 9) % 120)
    leg1_speed = 40 + ((index * 5) % 35)
    leg2_speed = 35 + ((index * 4) % 30)
    stop_minutes = 10 + ((index * 7) % 35)

    travel_time = (leg1_distance / leg1_speed) + (leg2_distance / leg2_speed) + (stop_minutes / 60)
    avg_speed = round((leg1_distance + leg2_distance) / travel_time, 2)

    prompt = (
        "A field engineer drives to two client sites in one route: "
        f"{leg1_distance} km at {leg1_speed} km/h, then {leg2_distance} km at {leg2_speed} km/h, "
        f"with a {stop_minutes}-minute stop between visits. "
        "What is the average speed for the entire journey?"
    )
    correct = f"{avg_speed} km/h"
    distractors = [
        f"{round((leg1_speed + leg2_speed) / 2, 2)} km/h",
        f"{round((leg1_distance + leg2_distance) / ((leg1_distance / leg1_speed) + (leg2_distance / leg2_speed)), 2)} km/h",
        f"{round(avg_speed + 8.5, 2)} km/h",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def _time_speed_distance_hard(topic: str, index: int) -> dict[str, Any]:
    route_a_distance = 220 + ((index * 14) % 190)
    route_b_distance = route_a_distance + (30 + (index % 50))
    route_a_speed = 55 + ((index * 3) % 35)
    route_b_speed = 70 + ((index * 2) % 40)

    route_a_time = round(route_a_distance / route_a_speed, 2)
    route_b_time = round(route_b_distance / route_b_speed, 2)

    better_route = "Route A" if route_a_time < route_b_time else "Route B"
    time_gap = round(abs(route_a_time - route_b_time), 2)

    prompt = (
        "A logistics planner is selecting the faster route for a same-day shipment. "
        f"Route A: {route_a_distance} km at {route_a_speed} km/h. "
        f"Route B: {route_b_distance} km at {route_b_speed} km/h. "
        "Ignoring breaks and traffic, which route is faster and by how much time?"
    )
    correct = f"{better_route} by {time_gap} hours"
    distractors = [
        f"Route A by {round(time_gap / 2, 2)} hours",
        f"Route B by {round(time_gap / 2, 2)} hours",
        "Both routes take the same time",
    ]
    return _build_mcq_rotating(topic, prompt, correct, distractors, index)


def generate_mcq_set(topic: str, difficulty: str, question_count: int, start_index: int = 0) -> list[dict[str, Any]]:
    normalized_topic = topic.strip()
    if not normalized_topic:
        raise ValueError("Topic is required")

    normalized_difficulty = difficulty.strip().lower()
    if normalized_difficulty not in {"easy", "medium", "hard"}:
        raise ValueError("Difficulty must be easy, medium, or hard")

    if question_count < 1:
        raise ValueError("Question count must be at least 1")

    if _is_algebra_topic(normalized_topic):
        generator = {
            "easy": _algebra_easy,
            "medium": _algebra_medium,
            "hard": _algebra_hard,
        }[normalized_difficulty]
    elif is_time_speed_distance_topic(normalized_topic):
        generator = {
            "easy": _time_speed_distance_easy,
            "medium": _time_speed_distance_medium,
            "hard": _time_speed_distance_hard,
        }[normalized_difficulty]
    else:
        generator = {
            "easy": _generic_easy,
            "medium": _generic_medium,
            "hard": _generic_hard,
        }[normalized_difficulty]

    return [generator(normalized_topic, idx) for idx in range(start_index, start_index + question_count)]
