import errno
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from aria.core import Action, ActionType as T, Verification
from aria.engine import Engine, ExecutionFailed
from aria.filesystem import (Files, FilesystemIdentityError, PathResolver,
                             same_content, snapshot)
from aria.parser import ClarificationRequired, UnsupportedCommand, parse
from aria.permissions import ConfirmationRequired, PermissionDenied, PermissionEngine


def pending(engine, action):
    with pytest.raises(ConfirmationRequired) as error:
        engine.execute(action)
    return error.value.pending


def resolver(tmp_path, known=None):
    known = known or tmp_path / "known"
    known.mkdir(exist_ok=True)
    return PathResolver(tmp_path, known_provider=lambda _name: known)


def test_resolver_captures_base_and_resolves_known_scoped_path(tmp_path, monkeypatch):
    known = tmp_path / "known"; known.mkdir(); item = known / "Report.TXT"; item.write_text("x")
    other = tmp_path / "other"; other.mkdir()
    paths = PathResolver(tmp_path, known_provider=lambda _name: known)
    monkeypatch.chdir(other)
    assert paths.existing("Report.TXT") == item
    assert paths.existing("documents/Report.TXT") == item
    assert paths.destination("new.txt") == tmp_path / "new.txt"


def test_bare_name_ambiguity_fails_closed(tmp_path):
    known = tmp_path / "known"; known.mkdir()
    (tmp_path / "same.txt").write_text("one"); (known / "same.txt").write_text("two")
    with pytest.raises(ClarificationRequired, match="ambiguous"):
        PathResolver(tmp_path, known_provider=lambda _name: known).existing("same.txt")


@pytest.mark.parametrize("value", [r"\\server\share\file.txt", r"C:\Temp\*.txt", r"C:\Temp\file.txt:secret", r"C:\Temp\NUL.txt"])
def test_unsafe_path_forms_are_rejected(tmp_path, value):
    with pytest.raises(ValueError): PathResolver(tmp_path).destination(value)


def test_snapshot_distinguishes_metadata_and_content(tmp_path):
    root = tmp_path / "tree"; root.mkdir(); (root / "a.bin").write_bytes(b"a" * 1024)
    metadata = snapshot(root, recursive_metadata=True)
    content = snapshot(root, recursive_metadata=True, content=True)
    assert metadata.metadata_sha256 and metadata.content_sha256 is None
    assert content.content_sha256 and content.entry_count == 2 and content.total_bytes == 1024
    clone = tmp_path / "clone"; Files._copy_new(root, clone)
    assert same_content(content, snapshot(clone, recursive_metadata=True, content=True))


def test_create_and_copy_are_verified_and_update_file_state(tmp_path):
    files = Files(resolver=resolver(tmp_path)); engine = Engine(files=files, shutdown=Mock())
    created = engine.execute(Action(T.CREATE_FOLDER, str(tmp_path), {"name": "New Folder"}))
    assert created.verification == Verification.VERIFIED
    assert engine.file_state.path == str(tmp_path / "New Folder")
    source = tmp_path / "source.bin"; source.write_bytes(os.urandom(4096))
    destination = tmp_path / "copy.bin"
    copied = engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert copied.verification == Verification.VERIFIED and destination.read_bytes() == source.read_bytes()
    assert copied.data["verification"] == "content" and copied.data["total_bytes"] == 4096
    assert engine.file_state.path == str(destination)


def test_copy_directory_is_content_verified(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "nested").mkdir()
    (source / "nested" / "data.txt").write_text("payload")
    destination = tmp_path / "destination"
    result = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock()).execute(
        Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert result.verification == Verification.VERIFIED
    assert result.data["entry_count"] == 3 and result.data["total_bytes"] == 7


def test_unconfirmed_copy_hashes_source_once_and_destination_once(tmp_path):
    source = tmp_path / "source.bin"; source.write_bytes(os.urandom(1024))
    destination = tmp_path / "destination.bin"
    class CountingFiles(Files):
        def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.content_snapshots = 0
        def snapshot(self, path, **options):
            if options.get("content"): self.content_snapshots += 1
            return snapshot(path, **options)
    files = CountingFiles(resolver=resolver(tmp_path))
    Engine(files=files, shutdown=Mock()).execute(
        Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert files.content_snapshots == 2


def test_existing_destination_is_never_overwritten(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("source")
    destination = tmp_path / "destination.txt"; destination.write_text("keep")
    engine = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock())
    with pytest.raises(FileExistsError):
        engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert destination.read_text() == "keep"


def test_copy_race_never_removes_an_external_destination(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("source")
    destination = tmp_path / "destination.txt"
    class RacingFiles(Files):
        @staticmethod
        def _copy_new(_source, raced_destination):
            raced_destination.write_text("external")
            raise FileExistsError(raced_destination)
    files = RacingFiles(resolver=resolver(tmp_path))
    with pytest.raises(FileExistsError):
        files.copy(source, destination)
    assert destination.read_text() == "external"


def test_rollback_refuses_an_output_changed_after_observation(tmp_path):
    output = tmp_path / "output.txt"; output.write_text("created")
    observed = snapshot(output, content=True)
    output.write_text("changed externally")
    files = Files(resolver=resolver(tmp_path))
    assert not files.rollback_created(output, observed)
    assert output.read_text() == "changed externally"


@pytest.mark.parametrize("kind", [T.MOVE_PATH, T.RENAME_PATH])
def test_move_and_rename_require_confirmation_and_verify_identity(tmp_path, kind):
    source = tmp_path / "source.txt"; source.write_text("payload")
    argument = str(tmp_path / "moved.txt") if kind == T.MOVE_PATH else "renamed.txt"
    engine = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock())
    request = pending(engine, Action(kind, str(source), {"destination": argument}))
    assert source.exists()
    result = engine.confirm(request.token)
    destination = tmp_path / ("moved.txt" if kind == T.MOVE_PATH else "renamed.txt")
    assert result.verification == Verification.VERIFIED and not source.exists() and destination.exists()
    assert result.data["verification"] == "identity" and engine.file_state.path == str(destination)


def test_changed_source_and_destination_parent_fail_confirmation(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("old")
    destination_parent = tmp_path / "destination"; destination_parent.mkdir()
    engine = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock())
    request = pending(engine, Action(T.MOVE_PATH, str(source), {"destination": str(destination_parent / "out.txt")}))
    source.write_text("changed")
    with pytest.raises(PermissionDenied, match="Target changed|changed"):
        engine.confirm(request.token)
    assert source.exists() and not (destination_parent / "out.txt").exists()


def test_replaced_destination_parent_fails_confirmation(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("old")
    destination_parent = tmp_path / "destination"; destination_parent.mkdir()
    engine = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock())
    request = pending(engine, Action(T.MOVE_PATH, str(source), {"destination": str(destination_parent / "out.txt")}))
    destination_parent.rmdir(); destination_parent.mkdir()
    with pytest.raises(PermissionDenied, match="Target changed|changed"):
        engine.confirm(request.token)
    assert source.exists()


def test_destination_appearing_after_copy_confirmation_fails_closed(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("source")
    destination = tmp_path / "destination.txt"
    engine = Engine(files=Files(resolver=resolver(tmp_path)),
                    permissions=PermissionEngine(confirm_low=True), shutdown=Mock())
    request = pending(engine, Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    destination.write_text("external")
    with pytest.raises(PermissionDenied): engine.confirm(request.token)
    assert destination.read_text() == "external"


def test_cross_volume_move_copies_verifies_then_removes(monkeypatch, tmp_path):
    source = tmp_path / "source.bin"; source.write_bytes(os.urandom(8192))
    destination = tmp_path / "destination.bin"
    import aria.filesystem as filesystem
    real_snapshot = filesystem.snapshot
    def volumes(path, **options):
        value = real_snapshot(path, **options)
        if Path(path) == destination.parent:
            return replace(value, identity=replace(value.identity, device=value.identity.device + 1))
        return value
    monkeypatch.setattr(filesystem, "snapshot", volumes)
    files = Files(resolver=resolver(tmp_path))
    engine = Engine(files=files, shutdown=Mock())
    request = pending(engine, Action(T.MOVE_PATH, str(source), {"destination": str(destination)}))
    result = engine.confirm(request.token)
    assert result.verification == Verification.VERIFIED and result.data["cross_volume"]
    assert destination.exists() and not source.exists()
    assert destination.stat().st_size == 8192


def test_delete_is_confirmed_observed_and_explicitly_unverified(tmp_path):
    target = tmp_path / "delete.txt"; target.write_text("disposable")
    files = Files(resolver=resolver(tmp_path)); files.delete = lambda value: Path(value).unlink()
    engine = Engine(files=files, shutdown=Mock())
    engine.file_state.update(str(target), snapshot(target).identity, "file", T.COPY_PATH, now=engine.clock())
    request = pending(engine, Action(T.DELETE_PATH, str(target)))
    result = engine.confirm(request.token)
    assert result.observed and result.verification == Verification.UNVERIFIED
    assert not engine.file_state.verified


def test_open_is_unverified_and_does_not_refresh_file_state(tmp_path):
    target = tmp_path / "open.txt"; target.write_text("x")
    files = Files(resolver=resolver(tmp_path)); files.open = Mock(return_value=target)
    engine = Engine(files=files, shutdown=Mock())
    result = engine.execute(Action(T.OPEN_PATH, str(target)))
    assert result.verification == Verification.UNVERIFIED and not engine.file_state.verified


def test_recent_file_is_ttl_bound_and_destructive_references_are_rejected(tmp_path):
    clock = [100.0]
    source = tmp_path / "source.txt"; source.write_text("x")
    destination = tmp_path / "copy.txt"
    files = Files(resolver=resolver(tmp_path)); files.open = Mock(return_value=destination)
    engine = Engine(files=files, shutdown=Mock(), clock=lambda: clock[0])
    engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert engine.execute(parse("open that file")).verification == Verification.UNVERIFIED
    clock[0] += 301
    with pytest.raises(ClarificationRequired, match="expired"):
        engine.execute(parse("open that file"))
    with pytest.raises((ClarificationRequired, UnsupportedCommand)):
        parse("delete that file")
    with pytest.raises(ClarificationRequired):
        parse('move file that to "C:\\Temp\\other.txt"')


def test_literal_command_words_inside_paths_do_not_form_compound_command():
    action = parse('copy file "C:\\Temp\\open and then delete.txt" to "C:\\Temp\\safe copy.txt"')
    assert action.kind == T.COPY_PATH
    assert action.target.endswith("open and then delete.txt")


def test_permission_failure_does_not_update_state(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("x")
    class DeniedFiles(Files):
        def copy(self, source, destination): raise PermissionError("denied")
    engine = Engine(files=DeniedFiles(resolver=resolver(tmp_path)), shutdown=Mock())
    with pytest.raises(PermissionError):
        engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(tmp_path / "out.txt")}))
    assert not engine.file_state.verified


def test_reparse_target_fails_closed_when_supported(tmp_path):
    target = tmp_path / "target.txt"; target.write_text("x")
    link = tmp_path / "link.txt"
    try: link.symlink_to(target)
    except OSError: pytest.skip("creating symlinks is unavailable on this Windows configuration")
    with pytest.raises(FilesystemIdentityError): Files.ensure_no_reparse(link)


def test_controlled_reparse_detection_fails_closed(monkeypatch, tmp_path):
    target = tmp_path / "target.txt"; target.write_text("x")
    monkeypatch.setattr("aria.filesystem._is_reparse", lambda _info: True)
    with pytest.raises(FilesystemIdentityError): Files.ensure_no_reparse(target)


def test_hardlinks_share_identity_without_redirecting_copy(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("shared content")
    alias = tmp_path / "alias.txt"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("creating hard links is unavailable on this Windows configuration")
    assert snapshot(source).identity == snapshot(alias).identity
    destination = tmp_path / "copy.txt"
    engine = Engine(files=Files(resolver=resolver(tmp_path)), shutdown=Mock())
    result = engine.execute(Action(T.COPY_PATH, str(alias), {"destination": str(destination)}))
    assert result.verification == Verification.VERIFIED
    assert source.read_text() == alias.read_text() == destination.read_text()


def test_verification_failure_rolls_back_exact_created_copy(tmp_path):
    source = tmp_path / "source.txt"; source.write_text("source")
    destination = tmp_path / "destination.txt"
    class CorruptingFiles(Files):
        def copy(self, source, destination):
            receipt = super().copy(source, destination)
            Path(destination).write_text("corrupt")
            return receipt
    engine = Engine(files=CorruptingFiles(resolver=resolver(tmp_path)), shutdown=Mock())
    with pytest.raises(ExecutionFailed) as error:
        engine.execute(Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    assert error.value.result.data["rollback_performed"]
    assert source.exists() and not destination.exists() and not engine.file_state.verified
