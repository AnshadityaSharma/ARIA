"""Pure tests: no microphone, commands, hotkeys, browser or other desktop actions."""
from dataclasses import FrozenInstanceError
import math
import queue
from unittest.mock import Mock
import pytest

from aria.shard_presentation import DisplayEvent as E, DisplayState as S, OutcomeStatus as O, PresentationModel, PresentationInbox
from aria.seam_presentation import (ActivityEvent, ActivityKind, SeamAdapter, SeamMotion,
                                     WorkArea, placement)
from aria.seam_ui import fit_text, font, seam_image
from scripts.phase8_seam_demo import SyntheticSource


@pytest.fixture
def rig():
    now = [0.]
    adapter = SeamAdapter(lambda: now[0])
    source = SyntheticSource(adapter)
    return now, adapter, source


def test_explicit_supersession_preserves_legacy_rejection():
    m = PresentationModel()
    assert m.apply(E("a", 0, S.LISTENING))
    assert not m.apply(E("b", 0, S.LISTENING))
    assert not m.apply(E("b", 0, S.LISTENING, supersedes="wrong"))
    assert m.apply(E("b", 0, S.LISTENING, supersedes="a"))
    assert not m.apply(E("a", 1, S.PARTIAL, 0, "old"))
    assert not m.apply(E("a", 0, S.LISTENING, supersedes="b"))


def test_string_outcome_is_not_an_authoritative_enum():
    m = PresentationModel()
    assert m.apply(E("a", 0, S.LISTENING))
    assert not m.apply(E("a", 1, S.FAILED, outcome="FAILED"))
    assert m.apply(E("a", 1, S.FAILED, outcome=O.FAILED))


@pytest.mark.parametrize("state", list(S))
def test_every_state_through_same_contract(rig, state):
    _, adapter, source = rig
    if state != S.IDLE:
        source.show(state)
    frame = adapter.advance()
    assert frame.snapshot.state == state
    if state == S.VERIFIED:
        assert frame.snapshot.outcome is O.VERIFIED


def test_fast_batch_coalesces_without_waiting_frames(rig):
    now, adapter, source = rig
    source.start()
    assert adapter.advance().compact_state == S.LISTENING
    source.send(S.FINAL, "Open Chrome", 0)
    source.send(S.PROCESSING)
    source.send(S.EXECUTING)
    source.send(S.VERIFIED)
    assert adapter.advance().compact_state == S.VERIFIED
    now[0] = 2
    frame = adapter.advance()
    assert frame.compact_state == S.IDLE
    assert frame.snapshot.outcome is O.VERIFIED
    assert frame.snapshot.transcript == "Open Chrome"


def test_delayed_wait_preempted_and_old_collapse_cannot_win(rig):
    now, adapter, source = rig
    source.show(S.PROCESSING)
    adapter.advance()
    now[0] = .179
    assert adapter.advance() is None
    now[0] = .180
    assert adapter.advance().compact_state == S.PROCESSING
    source.show(S.VERIFIED)
    adapter.advance()
    source.start()
    assert adapter.advance().compact_state == S.LISTENING
    now[0] = 9
    assert adapter.advance() is None
    assert adapter.compact_state == S.LISTENING


@pytest.mark.parametrize("state", [S.CONFIRMATION, S.FAILED, S.UNVERIFIED])
def test_important_states_persist_and_dismiss_without_authorizing(rig, state):
    now, adapter, source = rig
    source.show(state)
    assert adapter.advance().expanded
    now[0] = 60
    assert adapter.advance() is None
    adapter.dismiss()
    assert not adapter.advance().expanded
    assert adapter.latest.state == state


def test_activity_order_session_expiry_and_output_preserves_outcome(rig):
    now, adapter, source = rig
    source.show(S.VERIFIED)
    adapter.advance()
    event = ActivityEvent(source.session, 0, ActivityKind.OUTPUT, .5)
    assert adapter.submit_activity(event)
    assert adapter.advance().speaking
    assert adapter.latest.outcome is O.VERIFIED
    assert adapter.submit_activity(event)  # rejected on UI drain, not producer thread
    assert adapter.advance() is None
    assert adapter.rejected_activity == 1
    now[0] = .251
    assert not adapter.advance().speaking
    with pytest.raises(FrozenInstanceError):
        event.level = .9


@pytest.mark.parametrize("level", [-1, 2, math.nan, math.inf, True, "x"])
def test_invalid_activity(rig, level):
    _, adapter, _ = rig
    assert not adapter.submit_activity(ActivityEvent("a", 0, ActivityKind.INPUT, level))


def test_source_overflow_and_fault_never_create_outcome():
    inbox = PresentationInbox(source=queue.Queue(maxsize=1))
    adapter = SeamAdapter(inbox=inbox)
    assert adapter.submit(E("a", 0, S.LISTENING))
    assert not adapter.submit(E("a", 1, S.FINAL, 0, "overflow"))
    frame = adapter.advance()
    assert frame.fault == "Display event source unavailable"
    assert frame.snapshot.outcome is None
    assert frame.expanded


def test_shutdown_rejects_events_and_activity_without_execution(rig):
    _, adapter, source = rig
    source.show(S.CONFIRMATION)
    adapter.advance()
    adapter.close()
    assert adapter.advance() is None
    assert not source.start()
    assert not adapter.submit_activity(ActivityEvent("x", 0, ActivityKind.INPUT, .1))
    assert adapter.latest.transcript == ""


@pytest.mark.parametrize("dpi", [96, 120, 144, 192, 288])
def test_scaled_negative_monitor_and_tiny_workarea(dpi):
    area = WorkArea(-1280, 40, 0, 720, dpi)
    x, y, w, h = placement(area, 280, 178, 32)
    assert area.left <= x < x+w <= area.right
    assert area.top <= y < y+h <= area.bottom
    assert placement(WorkArea(0, 0, 20, 12), 280, 178) == (0, 0, 20, 12)
    with pytest.raises(ValueError):
        placement(WorkArea(0, 0, 0, 20), 2, 2)


def test_springs_retarget_without_velocity_reset_and_stop(rig):
    _, adapter, source = rig
    source.start()
    frame = adapter.advance()
    motion = SeamMotion()
    motion.retarget(frame)
    assert motion.step(.016)
    previous = motion.velocity["width"]
    motion.target["width"] = 124
    assert motion.velocity["width"] == previous
    for _ in range(200):
        moving = motion.step(.016)
    assert not moving
    assert motion.value["width"] == 124
    motion.target["width"] = 218
    assert not motion.step(.016, reduced=True)
    assert motion.value["width"] == 218
    with pytest.raises(ValueError):
        motion.step(math.nan)


@pytest.mark.parametrize("state", list(S))
def test_raster_all_states_contrast_long_text_bounds(rig, state):
    _, adapter, source = rig
    if state != S.IDLE:
        source.show(state, long=True)
    frame = adapter.advance()
    motion = SeamMotion()
    motion.retarget(frame)
    motion.step(0, reduced=True)
    image = seam_image(frame, motion.value, 1.5, contrast=True)
    assert image.width <= 327 and image.height <= 39
    assert image.getbbox()
    assert font(12).getlength(fit_text("long "*100, font(12), 150)) <= 150


def test_presentation_modules_have_no_command_dependency():
    import ast
    from pathlib import Path
    forbidden = {"aria.engine", "aria.activation", "aria.voice", "aria.parser", "aria.permissions", "aria.hotkey"}
    for name in ("seam_presentation.py", "seam_ui.py", "seam_windows.py", "shard_presentation.py"):
        tree = ast.parse((Path(__file__).parents[1]/"src/aria"/name).read_text())
        assert not any(isinstance(n, ast.ImportFrom) and n.module in forbidden for n in ast.walk(tree))


def test_motion_remains_bounded_after_slow_frames():
    motion = SeamMotion()
    motion.target["width"] = 218
    for _ in range(200):
        moving = motion.step(.1)
        assert 124 <= motion.value["width"] <= 218
    assert not moving and motion.value["width"] == 218


def test_adapter_malformed_identity_cannot_crash_submit():
    adapter = SeamAdapter()
    assert adapter.submit(E([], 0, S.LISTENING))
    assert adapter.advance().snapshot.session_id is None
    adapter.close()
    assert adapter.inbox.model.snapshot.transcript == ""
    assert adapter.inbox.source.empty()


@pytest.mark.parametrize("current", list(S))
@pytest.mark.parametrize("next_state", list(S))
def test_every_allowed_and_disallowed_state_edge(current, next_state):
    from aria.shard_presentation import TRANSITIONS, TERMINAL
    from scripts.phase8_seam_demo import SyntheticSource
    adapter = SeamAdapter()
    source = SyntheticSource(adapter)
    if current != S.IDLE:
        source.show(current)
        adapter.advance()
    model = adapter.inbox.model
    event = E(source.session or "fresh", source.sequence+1, next_state,
              2 if next_state in {S.PARTIAL, S.FINAL} else None,
              "revision" if next_state in {S.PARTIAL, S.FINAL} else None,
              O(next_state.value) if next_state in TERMINAL else None)
    assert model.apply(event) == (next_state in TRANSITIONS[current])
    adapter.close()
