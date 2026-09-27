from shop.settings import PAGE_SIZE
from shop.pagination import page
from shop.export_job import export_records


def test_export_respects_changed_page_size():
    assert PAGE_SIZE==3
    assert page(list(range(10)),1)==[3,4,5]
    assert export_records(list(range(10)))==list(range(10))
    assert export_records([])==[]
