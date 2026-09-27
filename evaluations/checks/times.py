from datetime import datetime,timezone,timedelta
from shop.time_format import timestamp
from shop.audit_sink import audit_time
from shop.time_reader import round_trip
import pytest


def test_utc_normalization():
    value=datetime(2026,1,1,2,tzinfo=timezone(timedelta(hours=2)))
    assert timestamp(value)=='2026-01-01T00:00:00Z'
    assert audit_time(value)['at']=='2026-01-01T00:00:00Z'
    assert round_trip(value)==datetime(2026,1,1,tzinfo=timezone.utc)
    with pytest.raises(ValueError):timestamp(datetime(2026,1,1))
