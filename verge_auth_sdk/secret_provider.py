import os
from functools import lru_cache


@lru_cache(maxsize=128)
def get_secret(name: str) -> str:
    """
    Universal secret provider supporting:
    - Local .env
    - AWS Secrets Manager
    - Azure Key Vault
    - Google Cloud Secret Manager
    - Oracle Cloud Vault
    """

    provider = os.getenv("SECRETS_PROVIDER", "env").lower()

    try:
        if provider == "env":
            return _from_env(name)

        if provider == "aws":
            return _from_aws(name)

        if provider == "azure":
            return _from_azure(name)

        if provider == "gcp":
            return _from_gcp(name)

        if provider == "oracle":
            return _from_oracle(name)

    except Exception as e:
        # fallback to environment variables
        value = os.getenv(name)
        if value:
            return value
        raise Exception(
            f"Secret '{name}' not found via provider '{provider}': {e}")

    raise Exception(f"Unknown SECRETS_PROVIDER '{provider}'")
