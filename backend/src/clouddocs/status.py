"""Document status state machine."""

from __future__ import annotations

from .errors import Conflict
from .models import DocumentStatus as S

_ALLOWED: dict[S, frozenset[S]] = {
    S.PENDING_UPLOAD: frozenset({S.UPLOADED, S.FAILED, S.DELETING}),
    S.UPLOADED: frozenset({S.INDEXING, S.FAILED, S.DELETING}),
    S.INDEXING: frozenset({S.READY, S.FAILED, S.DELETING}),
    S.READY: frozenset({S.DELETING}),
    S.FAILED: frozenset({S.DELETING}),
    S.DELETING: frozenset(),
}


def can_transition(current: S, new: S) -> bool:
    return new in _ALLOWED[current]


def ensure_transition(current: S, new: S) -> None:
    if not can_transition(current, new):
        raise Conflict(f"Cannot change document from {current.value} to {new.value}")
