from shop.shipping import shipping_price
from shop.shipping_invoice import shipping_invoice
from shop.shipping_config import EXPRESS,STANDARD


def test_current_branch_surcharge():
    assert EXPRESS==7 and STANDARD==2
    assert shipping_price(False)==2
    assert shipping_price(True)==9
    assert shipping_invoice(True)=={'shipping':9}
