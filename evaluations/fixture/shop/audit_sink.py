from .time_format import timestamp


def audit_time(value):
    return {'at':timestamp(value)}
