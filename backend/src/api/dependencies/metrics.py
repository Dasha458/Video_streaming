from src.schemas.metric import VIDEO_SEARCH_TOTAL


def video_search_metrics(category: str | None = None) -> bool:
    VIDEO_SEARCH_TOTAL.labels(category=category or "none").inc()
    return True
