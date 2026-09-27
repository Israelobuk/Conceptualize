from shop.slugs import slug
from shop.catalog import product_url
from shop.search_index import lookup_slug


def test_slug_consumers_share_normalization():
    assert slug('  New   Product!  ')=='new-product'
    assert product_url('New   Product!')=='/products/new-product'
    assert lookup_slug('New   Product!')=='new-product'
    assert slug('---A---')=='a'
