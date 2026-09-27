from evtx2es.models.Evtx2es import _create_normalized_event_data


def test_reason_is_always_text_without_changing_other_numeric_fields():
    assert _create_normalized_event_data(
        {"Reason": 3, "Count": 7, "ProcessId": "0x10"}
    ) == {"Reason": "3", "Count": 7, "ProcessId": 16}
    assert _create_normalized_event_data({"Reason": "Full Index Reset"}) == {
        "Reason": "Full Index Reset"
    }
    assert _create_normalized_event_data({"Reason": 2**64}) == {
        "Reason": str(2**64)
    }
