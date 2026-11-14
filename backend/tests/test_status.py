import pytest

from clouddocs.errors import Conflict
from clouddocs.models import DocumentStatus as S
from clouddocs.status import can_transition, ensure_transition


def test_happy_path():
    assert can_transition(S.PENDING_UPLOAD, S.UPLOADED)
    assert can_transition(S.UPLOADED, S.INDEXING)
    assert can_transition(S.INDEXING, S.READY)
    assert can_transition(S.READY, S.DELETING)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (S.PENDING_UPLOAD, S.READY),  # cannot skip indexing
        (S.UPLOADED, S.READY),
        (S.READY, S.INDEXING),
        (S.DELETING, S.READY),
        (S.FAILED, S.READY),
    ],
)
def test_illegal_transitions(a, b):
    assert not can_transition(a, b)
    with pytest.raises(Conflict):
        ensure_transition(a, b)
