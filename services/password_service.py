import re
import secrets


class PasswordService:
    def __init__(self, prefix: str = "$Manager", digits: int = 5):
        if digits != 5:
            raise ValueError("digits must be exactly 5")
        self.prefix = prefix
        self.digits = digits

    def generate(self) -> str:
        return f"{self.prefix}{''.join(secrets.choice('0123456789') for _ in range(self.digits))}"

    def is_valid(self, password: str) -> bool:
        return bool(re.fullmatch(re.escape(self.prefix) + r"\d{5}", password))
