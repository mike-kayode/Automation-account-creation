import re

from services.password_service import PasswordService


def test_password_has_required_pattern():
    password = PasswordService().generate()
    assert re.fullmatch(r"\$Manager\d{5}", password)
    assert PasswordService().is_valid(password)


def test_password_service_rejects_wrong_length():
    service = PasswordService()
    assert not service.is_valid("$Manager1234")
    assert not service.is_valid("$Manager123456")
