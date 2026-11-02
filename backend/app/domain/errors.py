"""Errors the ports raise, so callers never see an adapter's own exceptions."""


class MemoryNotConfiguredError(Exception):
    """Memory settings are missing, so nothing can be sent."""


class MemoryUnavailableError(Exception):
    """Memory was configured but the call failed."""


class DocumentNotFoundError(Exception):
    """No document with that id is visible to this key."""


class EntityNotFoundError(Exception):
    """No entity with that type and name is visible to this key."""


class UnsupportedDocumentError(Exception):
    """The file type can't be read, or the file holds no text."""
