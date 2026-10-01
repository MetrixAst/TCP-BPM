class Client1CError(Exception):
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class AuthenticationError(Client1CError):
    pass


class TokenExpiredError(Client1CError):
    pass


class APIError(Client1CError):
    pass


class ValidationError(Client1CError):
    pass


class MissingSupplierRequisitesError(Client1CError):
    """Ни 1С, ни фоллбэк-поля арендатора не дали банковские реквизиты для PDF."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)
