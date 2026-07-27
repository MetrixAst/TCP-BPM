class ESignerError(Exception):
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response


class ESignerAuthError(ESignerError):
    pass


class ESignerAPIError(ESignerError):
    pass