from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(ValueError):
    pass


class EncryptionService:
    def __init__(self, key: str):
        if not key:
            raise EncryptionError("ENCRYPTION_KEY is required")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise EncryptionError("ENCRYPTION_KEY must be a valid Fernet key") from error

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("ascii")

    def encrypt(self, value: str) -> str:
        if not value:
            raise ValueError("value must not be empty")
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError, ValueError) as error:
            raise EncryptionError("Unable to decrypt value") from error
