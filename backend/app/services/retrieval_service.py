
def get_allowed_visibility(user_role: str) -> list[str]:
    visibility_by_role = {
        "admin": ["public", "student", "staff", "admin"],
        "student": ["public", "student"],
        "staff": ["public", "staff"]
    }

    return visibility_by_role.get(user_role, ["public"])


def search_knowledge(
    question: str,
    db,
    user_role: str,
    limit: int = 5,
    min_similarity: float = 0.55
) -> list[dict]:
    # Document-based knowledge search is disabled.
    return []
