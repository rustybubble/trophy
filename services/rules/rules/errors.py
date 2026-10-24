class ConfigError(RuntimeError):
    """A required credential or setting is missing. Raised at client construction, never papered over."""
