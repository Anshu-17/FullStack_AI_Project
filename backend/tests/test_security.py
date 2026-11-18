from app.security import hash_password, verify_password


def test_password_is_hashed_not_stored_plain():
    h = hash_password("correct horse")
    assert "correct horse" not in h
    assert h.startswith("$2b$")


def test_verify_password():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", "not-a-real-hash")
