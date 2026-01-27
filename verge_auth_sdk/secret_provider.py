import os
from functools import lru_cache


class SecretNotFoundError(Exception):
    pass


# ----- Internal provider functions -----
def _from_env(name: str) -> str | None:
    return os.getenv(name)


def _from_aws(name: str) -> str:
    raise NotImplementedError("AWS Secrets Manager provider not implemented")


def _from_azure(name: str) -> str:
    raise NotImplementedError("Azure Key Vault provider not implemented")


def _from_gcp(name: str) -> str:
    raise NotImplementedError("GCP Secret Manager provider not implemented")


def _from_oracle(name: str) -> str:
    raise NotImplementedError("Oracle Cloud Vault provider not implemented")


PROVIDER_LOADERS = {
    "env": _from_env,
    "aws": _from_aws,
    "azure": _from_azure,
    "gcp": _from_gcp,
    "oracle": _from_oracle,
}


@lru_cache(maxsize=128)
def get_secret(name: str, *, required: bool = False) -> str | None:
    """
    Universal secret provider (soft-fail by default).

    If required=True → raises SecretNotFoundError
    If required=False → returns None
    """

    provider = os.getenv("SECRETS_PROVIDER", "env").lower()
    loader = PROVIDER_LOADERS.get(provider)

    if not loader:
        error = SecretNotFoundError(
            f"Unsupported SECRETS_PROVIDER '{provider}'"
        )
        if required:
            raise error
        return None

    # Try configured provider
    try:
        value = loader(name)

        if value is not None and value != "":
            return value

    except NotImplementedError:
        # Explicit signal → configuration error
        raise

    except Exception as e:
        provider_error = e
    else:
        provider_error = None

    # Fallback to env
    fallback = os.getenv(name)
    if fallback:
        return fallback

    # Soft fail or hard fail
    error = SecretNotFoundError(
        f"Secret '{name}' not found via provider '{provider}'"
        + (f": {provider_error}" if provider_error else "")
    )

    if required:
        raise error

    return None
