from relay.directory import lookup
from relay.ledger import ledger_key
def test_identity():
    assert lookup(" STRA\u1e9eE ", {"strasse": 7}) == 7
    assert ledger_key(" STRA\u1e9eE ") == "account:strasse"
