from app.services.counterparty_cache_service import fill_empty_phones_from_platform


def test_fill_empty_phones_from_platform_only_when_empty():
    class Row:
        def __init__(self, cp_id, phone):
            self.one_c_counterparty_id = cp_id
            self.phone = phone

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [
                Row("aaa-1", "+77001112233"),
                Row("bbb-2", "+77009998877, +77005554433"),
            ]

    class Db:
        def query(self, model):
            return Query()

    items = [
        {"id": "aaa-1", "phoneNumber": ""},
        {"id": "bbb-2", "phoneNumber": "+77000000000"},  # already from 1C — keep
        {"id": "ccc-3", "phoneNumber": ""},  # no platform phone
    ]
    filled = fill_empty_phones_from_platform(Db(), trc_id=2, items=items)
    assert filled == 1
    assert items[0]["phoneNumber"] == "+77001112233"
    assert items[1]["phoneNumber"] == "+77000000000"
    assert items[2]["phoneNumber"] == ""
