def run(attempt, count=2):
    for i in range(count):
        try:
            return attempt()
        except TimeoutError:
            if i == count - 1:
                raise
