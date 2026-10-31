from django.core.exceptions import ValidationError


class RequiredPasswordValidator:
    message = (
        "Use at least nine characters, including uppercase, lowercase, "
        "and a non-whitespace special character."
    )

    def validate(self, password, user=None):
        if not (
            len(password) >= 9
            and any(char.isupper() for char in password)
            and any(char.islower() for char in password)
            and any(not char.isalnum() and not char.isspace() for char in password)
        ):
            raise ValidationError(self.message, code="password_requirements")

    def get_help_text(self):
        return self.message
