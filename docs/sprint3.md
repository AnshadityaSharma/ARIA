# Sprint 3

Scope: global Ctrl+Space activation, status overlay, deterministic permission decisions,
single-use action-bound confirmation, and measured desktop lifecycle latency.

## Changes

New modules: `hotkey.py`, `activation.py`, `ui.py`, `permissions.py`.
Existing schema, parser, engine, voice timing, native windows, and file adapters
extended in place. New runtime dependencies: **none** (ctypes and bundled Tk).
Added `scripts/desktop_benchmark.py` and permission/lifecycle/desktop tests.

## Verification

Full unit and Windows suite: **58 passed** on 2026-09-22, with five existing
sounddevice/NumPy deprecation warnings. Compilation and diff checks passed.
The real-machine tests exercise Ctrl+Space delivery/unregistration, native window
operations, 100 ms real microphone capture, and actual Tk dialog buttons.
Cancel preserves disposable files; Confirm uses the Recycle Bin; timeout preserves
files. Shutdown is tested only with a mocked executor.

The integrated desktop benchmark injects Ctrl+Space and supplies locally synthesized
WAVs to the persistent Whisper model, existing parser, guarded engine, and native
Camera executor. Real microphone startup is measured separately. Confirmation
timings use a structured-action fixture and the real dialog/file executor.

These are automated real-UI checks, not a claim that a person clicked buttons or
spoke the sequence. Live speaker/accent acceptance remains a user validation step.

## Observed limitations

Camera enforced a 513 x 513 minimum in the final successful run. Exact 20% and further
10% shrink requests cannot go below that size. ARIA reports the constrained rectangle
and refreshes state; the top-right move works. An earlier Camera process crashed in
Windows.UI.Xaml.dll (Windows event 1000, exception 0xc000027b). ARIA refused follow-ups
to the missing window. A fresh launch completed the sequence.

ASR is the dominant latency cost. Its confidence score is heuristic, not a calibrated
probability. Spoken filenames may require careful pronunciation. Legacy CLI modes
remain available but interactive confirmation is provided in desktop mode.

The native adapter follows [Microsoft RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey).
Tk operations stay on the main thread; see [Python Tk threading](https://docs.python.org/3/library/tkinter.html#threading-model).
