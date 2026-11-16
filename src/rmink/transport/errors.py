"""What can go wrong moving a notebook, the same for every transport."""

from __future__ import annotations


class TransportError(Exception):
    """The transport failed; the message is safe to show to the user."""


class AuthError(TransportError):
    """Not connected: the token is missing, revoked or expired, or no
    transport is set up."""


class ExistsError(TransportError):
    """Something with the same name is already in the target folder."""


class NotFoundError(TransportError):
    """The path does not exist."""
