from app.providers.runexis.parser import is_numbering_free_status


def test_numbering_free_status_allowlist():
    assert is_numbering_free_status("free") is True
    assert is_numbering_free_status("Free") is True
    assert is_numbering_free_status("0") is True
    assert is_numbering_free_status(0) is True
    assert is_numbering_free_status(None) is True
    assert is_numbering_free_status("") is True


def test_numbering_free_status_rejects_non_free():
    assert is_numbering_free_status("4") is False
    assert is_numbering_free_status(4) is False
    assert is_numbering_free_status("3") is False
    assert is_numbering_free_status("sold") is False
    assert is_numbering_free_status("installed") is False
    assert is_numbering_free_status("reserved") is False
    assert is_numbering_free_status("booked") is False
