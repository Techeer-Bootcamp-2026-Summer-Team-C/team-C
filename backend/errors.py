class ApplicationError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or []


class AgentIdentityConflictError(ApplicationError):
    def __init__(self, message: str = "Agent identity conflicts with an existing Endpoint.") -> None:
        super().__init__(409, "IDENTITY_CONFLICT", message)


class EndpointRetiredError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(403, "ENDPOINT_RETIRED", "The Endpoint is retired.")


class InvalidAgentCertificateError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(401, "INVALID_AGENT_CERTIFICATE", "The Agent certificate is not active.")


class ServiceUnavailableError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(503, "SERVICE_UNAVAILABLE", message, True)


class PayloadTooLargeError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(413, "PAYLOAD_TOO_LARGE", message)


class RequestValidationError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "VALIDATION_ERROR", message)


class ArchivedDayImmutableError(Exception):
    pass
