"""Deterministic, execution-free checks for the Phase 8B display contract."""

from dataclasses import FrozenInstanceError
from unittest.mock import Mock
import pytest

from aria.shard_presentation import (DisplayEvent, DisplayState as S,
                                     OutcomeStatus as O, PresentationInbox,
                                     PresentationModel)


def event(n, state, *, session="one", revision=None, text=None, outcome=None):
    return DisplayEvent(session, n, state, revision, text, outcome)


def test_legal_lifecycle_and_explicit_verified_outcome():
    model = PresentationModel()
    path = [event(0, S.LISTENING), event(1, S.PARTIAL, revision=1, text="Move"),
            event(2, S.FINAL, revision=2, text="Move window"),
            event(3, S.PROCESSING), event(4, S.CONFIRMATION),
            event(5, S.EXECUTING), event(6, S.VERIFIED, outcome=O.VERIFIED)]
    assert all(model.apply(item) for item in path)
    assert model.snapshot.outcome == O.VERIFIED
    assert model.snapshot.transcript == "Move window"
    assert model.apply(event(7, S.IDLE))
    assert model.apply(event(0, S.LISTENING, session="two"))
    assert model.snapshot.transcript == ""


@pytest.mark.parametrize("state,outcome", [(S.FAILED, O.FAILED),
                                           (S.CANCELLED, O.CANCELLED)])
def test_failure_and_cancellation_from_listening(state, outcome):
    model = PresentationModel()
    assert model.apply(event(0, S.LISTENING))
    assert model.apply(event(1, state, outcome=outcome))
    assert model.snapshot.outcome == outcome


def test_unverified_is_not_success():
    model = PresentationModel()
    assert model.apply(event(0, S.LISTENING))
    assert model.apply(event(1, S.PROCESSING))
    assert model.apply(event(2, S.EXECUTING))
    assert not model.apply(event(3, S.VERIFIED))
    assert not model.apply(event(3, S.VERIFIED, outcome=O.UNVERIFIED))
    assert model.apply(event(3, S.UNVERIFIED, outcome=O.UNVERIFIED))
    assert model.snapshot.outcome == O.UNVERIFIED


def test_stale_duplicate_and_out_of_order_updates_are_ignored():
    model = PresentationModel()
    assert model.apply(event(0, S.LISTENING))
    assert not model.apply(event(2, S.PARTIAL, revision=1, text="late"))
    assert model.apply(event(1, S.PARTIAL, revision=2, text="new"))
    before = model.snapshot
    assert not model.apply(event(1, S.PARTIAL, revision=2, text="duplicate"))
    assert not model.apply(event(2, S.PARTIAL, revision=2, text="stale revision"))
    assert model.snapshot == before
    assert model.apply(event(2, S.FINAL, revision=2, text="final"))
    assert not model.apply(event(3, S.PARTIAL, revision=3, text="late partial"))
    assert model.snapshot.transcript == "final"


def test_empty_final_replaces_partial_and_long_text_is_bounded():
    model = PresentationModel()
    assert model.apply(event(0, S.LISTENING))
    assert model.apply(event(1, S.PARTIAL, revision=1, text="guess"))
    assert model.apply(event(2, S.FINAL))
    assert model.snapshot.transcript == ""
    second = PresentationModel()
    assert second.apply(event(0, S.LISTENING))
    assert not second.apply(event(1, S.PARTIAL, revision=1, text="x" * 10001))
    assert second.apply(event(1, S.PARTIAL, revision=1, text="x" * 10000))


def test_invalid_transition_and_old_session_rejected():
    model = PresentationModel()
    assert not model.apply(event(0, S.EXECUTING))
    assert model.apply(event(0, S.LISTENING))
    assert not model.apply(event(1, S.VERIFIED, outcome=O.VERIFIED))
    assert not model.apply(event(0, S.LISTENING, session="another"))
    assert model.apply(event(1, S.CANCELLED, outcome=O.CANCELLED))
    assert model.apply(event(0, S.LISTENING, session="another"))
    assert not model.apply(event(2, S.PARTIAL, session="one", revision=1, text="old"))


@pytest.mark.parametrize("bad", [None, object(), DisplayEvent("", 0, S.LISTENING),
                                  DisplayEvent("one", -1, S.LISTENING),
                                  DisplayEvent("one", True, S.LISTENING),
                                  DisplayEvent("one", 0, "LISTENING"),
                                  DisplayEvent("one", 0, S.LISTENING, 1, "words"),
                                  DisplayEvent("one", 0, S.LISTENING, outcome=O.VERIFIED),
                                  DisplayEvent("one", 0, S.PARTIAL, None, "words")])
def test_malformed_event_is_rejected_without_mutation(bad):
    model = PresentationModel()
    assert not model.apply(bad)
    assert model.snapshot.state == S.IDLE


def test_immutable_events_no_execution_hook_and_clean_close():
    command = Mock()
    model = PresentationModel()
    item = event(0, S.LISTENING)
    with pytest.raises(FrozenInstanceError):
        item.state = S.EXECUTING
    assert model.apply(item)
    model.close()
    assert not model.apply(event(1, S.PROCESSING))
    command.assert_not_called()


def test_inbox_bounded_drain_and_clean_shutdown():
    inbox = PresentationInbox()
    assert inbox.submit(event(0, S.LISTENING))
    assert inbox.submit(event(1, S.PARTIAL, revision=1, text="sample"))
    assert inbox.drain(limit=1) == 1
    assert inbox.model.snapshot.state == S.LISTENING
    assert inbox.drain() == 1
    inbox.close()
    assert not inbox.submit(event(2, S.FINAL, revision=2, text="sample"))
    assert inbox.drain() == 0


def test_event_source_failure_does_not_change_outcome():
    broken = Mock()
    broken.put_nowait.side_effect = RuntimeError("private source detail")
    inbox = PresentationInbox(source=broken)
    assert not inbox.submit(event(0, S.LISTENING))
    assert inbox.error == "Display event source unavailable"
    assert inbox.model.snapshot.outcome is None
    broken_get = Mock()
    broken_get.get_nowait.side_effect = RuntimeError("private source detail")
    inbox = PresentationInbox(source=broken_get)
    assert inbox.drain() == 0
    assert inbox.error == "Display event source unavailable"
    assert inbox.model.snapshot.outcome is None


def test_synthetic_gallery_states_and_bounded_copy():
    from scripts.phase8_shard_demo import clipped_lines, synthetic_snapshot
    for state in S:
        snapshot = synthetic_snapshot(state, long_text=True)
        assert snapshot.state == state
        if state == S.VERIFIED:
            assert snapshot.outcome == O.VERIFIED
    assert clipped_lines("long " * 100).endswith("…")
    assert len(clipped_lines("long " * 100).splitlines()) == 3
