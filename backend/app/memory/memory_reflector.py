from app.memory.memory_store import MemoryCandidate, detect_operating_lesson_candidate


def reflect_message_into_memory_candidate(message: str) -> MemoryCandidate | None:
    """Turn Victor's corrections into short reusable operating rules.

    This keeps Eva from storing raw complaints or prompts while still learning how
    Victor wants her to behave.
    """

    return detect_operating_lesson_candidate(message)
