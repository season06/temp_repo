class RagAdapterError(Exception):
    error_code = "rag_adapter_error"
    retryable = False


class ConfigurationError(RagAdapterError):
    error_code = "configuration_error"


class IngestionError(RagAdapterError):
    error_code = "ingestion_error"


class ProviderError(RagAdapterError):
    error_code = "provider_error"
    retryable = True

