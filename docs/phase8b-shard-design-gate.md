# Phase 8B Shard design gate — visual review candidate

Status: **awaiting visual selection**. This is a synthetic Tk design gallery and a
presentation-only event contract. It is not connected to voice, activation, the
command engine, or the safety kernel. No concept is selected for the product.

## Run and compare

From this worktree root, run `python scripts/phase8_shard_demo.py`. Tk is part of
the existing Python stack; no additional package is needed for the gallery. The
three concepts appear together. Choose any state from the selector; use the
Expanded, Long transcript, High contrast, and Reduced motion controls. The right
arrow advances states; Tab reaches the controls; Escape closes the gallery. The
full transcript button opens selectable complete text. Every shown transcript is
synthetic, including the partial revision. The demo contains no command input,
hotkey, microphone, executor, or approval control.

| Direction | Silhouette and layout | Strength | Main concern |
| --- | --- | --- | --- |
| 01 Split Prism | Offset horizontal blades separated by a narrow negative-space seam; left rail beside a compact rectangular status panel | Legible at small size; status and text align naturally with the mark | Angular two-part mark may need care at 100% scaling to keep the seam visible |
| 02 Folded Kite | Single tall asymmetric kite with a cutout; centered mark above the transcript card | Strong icon silhouette and quiet idle presence | Taller expansion may overlap content near the bottom of a screen |
| 03 Cutline | Three open directional plates with a detached lower segment; segmented status strip | Original open silhouette and strong direction of motion | More small edges to resolve at low DPI; least compact logo candidate |

**Recommendation for review:** Split Prism is the strongest starting direction
for a compact floating surface. Its horizontal form has room for a short status
and avoids the height of Folded Kite. Folded Kite merits a second look as the
application icon; Cutline is the most distinctive but carries a scaling risk.
This is a recommendation, not a final selection.

## State and motion language

All three concepts display an explicit text label for idle, listening, partial
and final transcript, processing, confirmation, executing, verified result,
failure, cancellation, and unverified outcome. Color reinforces those labels;
it never supplies their only meaning. A state change gives the card edge one
brief, three-frame reveal (90 ms total); a newer state cancels the remaining
frames. Reduced motion renders the same labeled state immediately without the
reveal. There is no idle pulse or continuous waveform. A later selected design
could add a short panel expansion, but that motion is unimplemented and needs
visual and resource review.

The gallery's compact and expanded cards are comparative mock surfaces, not a
native overlay. Long text is clamped to three lines in the card, with a separate
selectable full-text view. The underlying presentation snapshot retains the
complete text up to 10,000 characters. A production UI needs an approved
privacy rule for how long transcript text remains visible and retained.

## Presentation contract groundwork

`DisplayEvent` is immutable and includes a session ID, monotonically adjacent
sequence number, explicit `DisplayState`, optional transcript revision and
text, and optional explicit `OutcomeStatus`. `PresentationModel` accepts a new
session only at listening sequence zero, rejects repeated or stale sessions,
duplicates, gaps, invalid transitions, malformed payloads, and stale partial
revisions. A final event can replace a partial with newer text or clear it when
no final text is available. Terminal states require the corresponding explicit
`VERIFIED`, `FAILED`, `CANCELLED`, or `UNVERIFIED` outcome. A generic result or
completion event never produces verified success by inference. The model has no
callback capable of executing a command.

This model is a prototype contract proposal. Future integration must review
how the authoritative Phase 6/7 source supplies session identity, final text,
cancel status, and the engine's verification value. The current Phase 6 path is
final-only; actual partials are neither available nor implied by this demo.
The current engineering overlay and confirmation dialog remain untouched.

## Windows and accessibility review still needed

This gallery is a normal Tk window and may take focus when launched. It does
not claim no-activate overlay behavior, monitor work-area placement, DPI
correctness, taskbar/full-screen handling, screen-reader announcement quality,
or native high-contrast detection. These belong to the later presentation
implementation and manual Windows review. The High contrast control previews
a black/white/yellow treatment but does not follow system settings. The
Reduced motion control suppresses the brief edge reveal.

No timer runs while the gallery is idle. The only scheduled frames are the
three-frame state reveal; no performance or resource claim follows from this alone.
Future measurement should compare existing overlay and candidates on startup,
event-to-first-useful-frame, hidden/active CPU and working set, process count,
GPU use, and command-path impact against the proposed budgets in `context.md`.

## Visual decision requested

Select 01, 02, 03, or ask for a specific revision or hybrid. After that
decision, the next increment can build the chosen presentation layer and
measure native Windows behavior. Connecting live activation or execution events
requires a separate integration review.
