def retry(attempt, maximum=3):
    last = None
    for _ in range(maximum):
        try:
            return attempt()
        except TimeoutError as exc:
            last = exc
    raise last
