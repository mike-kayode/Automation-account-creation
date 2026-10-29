import pytest

from services.encryption_service import EncryptionError, EncryptionService


def test_encrypt_decrypt_round_trip():
    service = EncryptionService(EncryptionService.generate_key())
    encrypted = service.encrypt("$Trader12345")
    assert encrypted != "$Trader12345"
    assert service.decrypt(encrypted) == "$Trader12345"


def test_invalid_key_is_rejected():
    with pytest.raises(EncryptionError):
        EncryptionService("not-a-fernet-key")
