from shop.customer_keys import key
from shop.customer_store import find_customer
from shop.segment_writer import customer_bucket


def test_unicode_casefold():
    assert key(' STRAẞE@EXAMPLE.COM ') == 'strasse@example.com'
    assert find_customer('A@B.COM',{'a@b.com':'found'})=='found'
    assert customer_bucket(' A@B.COM ')=='a@b.com'
