"""HTTP client for the external payment provider."""

import httpx

from app.config import get_settings
from app.exceptions import ProviderUnavailableError
from app.schemas import ProviderPaymentResponse


class ProviderClient:
    """Async client for the provider payment API.

    Owns a single HTTP connection pool for the process lifetime;
    call aclose() on shutdown.
    """

    def __init__(self, provider_url: str = get_settings().provider_url) -> None:
        """Bind the client to the provider base URL.

        Args:
            provider_url: Provider base URL;
                defaults to the PROVIDER_URL setting.
        """
        self.provider_url = provider_url
        self._client = httpx.AsyncClient(base_url=self.provider_url, timeout=10)

    async def create_payment(
        self,
        operation_id: str,
        amount: str,
        currency: str,
    ) -> ProviderPaymentResponse:
        """Create a payment for an operation, idempotently.

        Sends POST /payments with Idempotency-Key and X-Correlation-ID
        equal to the opreation id, so a retry with the same arguments
        returns the same payment instead of creating a second one.

        Args:
            operation_id: Operation id, also used as the idempotency key.
            amount: Decimal string with two fraction digits, e.g. "1000.00";
                must be byte-identical across retries of one operation.
            currency: Currenct code, e.g. "RUB".

        Returns:
            Parsed provider response with the provider payment id.

        Raises:
            ProviderUnavailableError: Network failure or 5xx response.
                The payment may or may not have been created; retry
                later with the same arguments.
            httpx.HTTPStatusError: 4xx response, i.e. an invalid request;
                retrying the same request will not help.
        """
        try:
            response = await self._client.post(
                "/payments",
                headers={
                    "Idempotency-Key": operation_id,
                    "X-Correlation-ID": operation_id,
                },
                json={
                    "operationId": operation_id,
                    "amount": amount,
                    "currency": currency,
                },
            )
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        if response.status_code >= 500:
            raise ProviderUnavailableError(f"provider returned {response.status_code}")

        response.raise_for_status()

        return ProviderPaymentResponse.model_validate(response.json())

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()
