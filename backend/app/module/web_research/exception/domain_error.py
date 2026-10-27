"""Domain errors for the web research slice.

Error messages travel back to the caller (an agent tool or HTTP) through the
global envelope, so the strings here **must not** contain an API key, an
Authorization header, or a raw provider response header. The key only exists in
server memory and in the header of the Tavily request.
"""


class WebResearchError(Exception):
    """Base class for every web-research failure."""


class WebSearchNotConfiguredError(WebResearchError):
    def __init__(self) -> None:
        super().__init__("No web search provider is configured for this instance.")


class WebFetchNotConfiguredError(WebResearchError):
    def __init__(self) -> None:
        super().__init__("No web fetch provider is configured for this instance.")


class WebUrlInvalidError(WebResearchError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class WebProviderAuthenticationError(WebResearchError):
    def __init__(self, provider: str, status_code: int) -> None:
        # Only the provider name and the status code are included; the provider
        # response is never echoed, so no header or key fragment can leak out in the
        # exception message.
        super().__init__(f"The {provider} provider rejected the API key (HTTP {status_code}).")


class WebProviderError(WebResearchError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"The web provider failed: {detail}")
