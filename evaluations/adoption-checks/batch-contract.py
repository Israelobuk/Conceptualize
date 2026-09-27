from relay.settings import BatchPolicy
from relay.admission import admit
from relay.bootstrap import worker_options
from dataclasses import is_dataclass
def test_policy():
    assert is_dataclass(BatchPolicy) and BatchPolicy.__dataclass_params__.frozen
    assert BatchPolicy().maximum == 25
    assert worker_options() == {"maximum_batch": 25}
    assert admit(25) and admit(1)
    assert all(not admit(v) for v in [True, 0, -1, 26, 2.5])
