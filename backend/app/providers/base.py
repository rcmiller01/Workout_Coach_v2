"""
AI Fitness Coach v1 — Base Provider Interface

All external system adapters implement this pattern:
- Async HTTP client (httpx)
- Retry logic with tenacity
- Typed return values
- Graceful degradation when service is unavailable
"""
from abc import ABC, abstractmethod
from typing import Optional, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, provider: str, message: str, status_code: Optional[int] = None):
        self.provider = provider
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class ProviderUnavailableError(ProviderError):
    """Raised when a provider service is not reachable."""
    pass


class BaseProvider(ABC):
    """
    Abstract base class for external system providers.

    Subclasses implement the specific API calls for wger, Tandoor, etc.
    """

    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
        return self._client

    @abstractmethod
    def _auth_headers(self) -> dict[str, str]:
        """Return authentication headers for this provider."""
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict | list:
        """Make an authenticated request to the provider API."""
        client = await self.get_client()
        try:
            response = await client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise ProviderUnavailableError(
                self.provider_name,
                f"Cannot connect to {self.base_url}",
            )
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                self.provider_name,
                f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                status_code=e.response.status_code,
            )

    async def get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        return await self._request("GET", endpoint, params=params)

    async def post(self, endpoint: str, json: Optional[dict] = None) -> Any:
        return await self._request("POST", endpoint, json=json)

    async def put(self, endpoint: str, json: Optional[dict] = None) -> Any:
        return await self._request("PUT", endpoint, json=json)

    async def patch(self, endpoint: str, json: Optional[dict] = None) -> Any:
        return await self._request("PATCH", endpoint, json=json)

    async def delete(self, endpoint: str) -> Any:
        return await self._request("DELETE", endpoint)

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider service is available."""
        ...

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
