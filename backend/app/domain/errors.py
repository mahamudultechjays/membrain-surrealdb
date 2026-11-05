"""Errors the ports raise, so callers never see an adapter's own exceptions."""


class MemoryNotConfiguredError(Exception):
    """Memory settings are missing, so nothing can be sent."""


class MemoryUnavailableError(Exception):
    """Memory was configured but the call failed."""


class DocumentNotFoundError(Exception):
    """No document with that id is visible to this key."""


class EntityNotFoundError(Exception):
    """No entity with that type and name is visible to this key."""


class ScopeNotGrantedError(Exception):
    """The user holds no grant that allows this on that scope."""


class UnsupportedDocumentError(Exception):
    """The file type can't be read, or the file holds no text."""


class UnknownVctNodeError(Exception):
    """A VCT node id that is not on the metro map, or an invalid node choice."""


class VctNotSeededError(Exception):
    """The VCT matcher scope returned nothing: the nodes have not been seeded."""
