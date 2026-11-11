class ApplicationError(Exception):
    """Base class for failures a use case reports to its caller."""


class NotFound(ApplicationError):
    pass


class Conflict(ApplicationError):
    pass


class InvalidInput(ApplicationError):
    pass


class InvalidPdf(ApplicationError):
    """A document cannot be read as a PDF. Retrying will not help."""
