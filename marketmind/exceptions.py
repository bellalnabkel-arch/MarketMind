"""Domain-specific exceptions used by MarketMind."""


class MarketMindError(Exception):
    """Base exception for expected application errors."""


class DataSourceError(MarketMindError):
    """Raised when a remote data source cannot be read or parsed."""

    def __init__(self, message, *, code="provider_error", status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class TickerNotFoundError(DataSourceError):
    """Raised when a ticker cannot be resolved through SEC metadata."""


class FREDConfigurationError(DataSourceError):
    """Raised when FRED access is requested without an API key."""


class ModelValidationError(MarketMindError):
    """Raised when valuation assumptions are mathematically invalid."""
