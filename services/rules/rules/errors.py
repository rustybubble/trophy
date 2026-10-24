class ConfigError(RuntimeError):
    """A required credential or index is missing. The service exits 3 on it; there is no keyless mode."""
