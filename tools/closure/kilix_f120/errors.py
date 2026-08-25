"""Typed failures with stable, non-secret diagnostics."""


class ClosureError(RuntimeError):
    """Base class for an expected F120 refusal."""


class ContractError(ClosureError):
    """A frozen-contract or semantic-policy check failed."""


class RegistrationError(ClosureError):
    """An implementation registration is incomplete or malformed."""


class GitError(ClosureError):
    """A bounded Git operation failed."""


class CacheError(ClosureError):
    """A source or build cache operation failed closed."""


class BuildError(ClosureError):
    """A provider build or staged-prefix audit failed."""
