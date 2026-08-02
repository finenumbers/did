class ProviderError(Exception):
    """Base provider error."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR", details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ProviderContractError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_CONTRACT_ERROR", **kwargs)


class ProviderNotImplementedError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_NOT_IMPLEMENTED", **kwargs)


class ProviderCapabilityLimitedError(ProviderError):
    """Documentation does not confirm a required capability."""

    def __init__(self, message: str, *, provider: str, capability: str, doc_refs: list[str] | None = None):
        super().__init__(
            message,
            code="PROVIDER_CAPABILITY_LIMITED",
            details={"provider": provider, "capability": capability, "doc_refs": doc_refs or []},
        )
        self.provider = provider
        self.capability = capability


class ProviderAuthError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_AUTH_ERROR", **kwargs)


class ProviderTransportError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_TRANSPORT_ERROR", **kwargs)


class ProviderParseError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_PARSE_ERROR", **kwargs)


class ProviderMappingError(ProviderError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="PROVIDER_MAPPING_ERROR", **kwargs)
