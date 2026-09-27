from datetime import datetime
from .time_format import timestamp


def round_trip(value):
    return datetime.fromisoformat(timestamp(value))
