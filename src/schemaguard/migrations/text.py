MAX_TEXT_LENGTH: int = 80


def short(sql: str) -> str:
    text = " ".join(sql.split())

    if len(text) <= MAX_TEXT_LENGTH:
        return text

    return text[:MAX_TEXT_LENGTH] + "..."
