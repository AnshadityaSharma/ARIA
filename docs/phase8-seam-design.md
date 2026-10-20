# ARIA Seam — selected design and presentation specification

Status: **Seam selected by the user; refined standalone prototype delivered.**
Date: 2026-10-12.

The user's selection supersedes the earlier requirement to preserve a literal
Shard silhouette. The product identity is now the Seam: a narrow light at the
screen edge, a quiet optional transcript, and a small inspection surface.
This records the visual decision. It does not mark Phase 8 or native Windows
presentation accepted.

## Deliverables and use

- `scripts/phase8_seam_final.html`: single-file offline interactive prototype.
- `tests/phase8_seam_checks.cjs`: dependency-free behavior checks.
- This document: dimensions, motion, outcomes, and remaining native gates.

Open the HTML in a modern browser at its normal zoom. The top-center Seam is
drawn at actual CSS size, without a desktop scaling transform. The underlying
browser/document is a sample backdrop. The controls at bottom left belong to
the prototype, not to the ARIA product. Hide them to examine the presence alone.
Browser zoom and OS display scaling still affect physical size; this is not a
physical-inch or native DPI measurement.

Hover to inspect, click the Seam to keep details open, or Tab to the Seam.
Enter/Space toggles pinning; Arrow Down enters the selectable transcript.
Close or Esc collapses details. Esc does not authorize or confirm an action.
Confirm/Cancel are scoped synthetic buttons. The prototype never captures a
microphone, outputs speech, or executes a desktop command.

## Visual design

| Element | Chosen treatment |
| --- | --- |
| Placement | Top center, flush to the preview's top edge |
| Resting bounds | 124 × 23 CSS px; an optional minimal-idle mode reduces height to 8 px |
| Active caption bounds | 218 × 26 CSS px |
| Main light | 2 px line with a short bright segment and restrained local reflection |
| Caption | 10 px Segoe UI, one subdued line, ellipsis for overflow |
| Idle wordmark | 9 px, reduced opacity |
| Inspection width | 280 px, bounded to viewport width minus 24 px |
| Inspection transcript | 12 px, selectable, wraps, scrolls above 76 px height |
| Supporting message | 10.5 px, bounded to 66 px height |
| Material | Dark translucent edge; stable, self-contained opaque detail surface |
| Palette | Cool white and muted mint; amber and warm error accents reinforce labels |

Identity comes from the line, its position, its response, and its proportions.
Keep expansion small and purposeful. Avoid adding a large animated emblem,
decorative gauges, particles, constant sweeps, or a wide banner. A future app
icon can use the short seam cut; no separate icon is finalized here.

## Motion and latency

- Width retargets with a 150 ms eased transition; disclosure fades in 100 ms
  and settles over 140 ms. These are chosen design timings, not measurements.
- A critically damped spring moves the bright segment. New targets preserve
  existing velocity; a new session does not restart a fixed animation clip.
- Simulated voice changes segment length and lateral offset. Silence settles
  the segment and stops the frame loop. Idle and hidden presentation have no
  recurring animation-frame request from this implementation.
- Reduced motion uses static poses and immediate disclosure. Native reduced
  motion, frame pacing, and CPU/RAM still require measurement.
- Processing/executing display waits 180 ms. Their underlying synthetic events
  are accepted immediately. If the state has already changed, the delayed
  indicator is discarded. A fast final → executing → verified sequence renders
  the result without requiring visible intermediate steps.
- Verified feedback and its caption remain readable for 1,300 ms; cancellation
  retracts after 450 ms. These holds never gate actions and can be interrupted
  by a new command. Failure, confirmation, and unverified outcomes do not
  silently disappear on a success-style timer.
- Pause freezes the synthetic scenario clock and animation. This is a review
  tool only; a production presentation must never pause the command pipeline.

## State and disclosure contract

| State | Compact signal | Expanded meaning |
| --- | --- | --- |
| Idle | Still hairline and subtle `aria`; optional 8 px minimal mode | Last transcript and explicit last terminal status remain inspectable |
| Listening | Open light segment; moves only during synthetic activity | Listening label and available transcript |
| Partial | Same listening identity; complete hypothesis replaced | No word highlighting or claim of real streaming ASR |
| Final | Stable caption | Complete recognized text; absent final text clears stale partial |
| Processing | Static `…`, only if still current after 180 ms | Waiting for result; no invented percentage |
| Executing | Static `↗`, only if still current after 180 ms | Action in progress |
| Confirmation | Bounded light with `!`; inspection opens | Specific pending decision and labeled buttons |
| Verified | Joined light and explicit check | Verified, only from a matching explicit result |
| Failure | Broken light and `!`; inspection opens | Specific error, remains until dismissed or superseded |
| Cancelled | Neutral retract and `−` | Cancelled; no success flash |
| Unverified | Fine open gap and `?`; inspection opens | Action ran, result could not be checked |
| Speaking | Optional synthetic output timing drives segment | Speaking · simulated; no audio or TTS integration |

The 15-second confirmation expiry is a synthetic demo choice. Production must
use the safety kernel's actual expiry and confirmation binding. Clicking a demo
button does not prove any target, permission, or action has been approved.

Caption visibility is independent from transcript availability. Turning off the
caption keeps the transcript in the inspection view. Long text never increases
the compact surface. Text is kept only in this page's memory; reset clears it,
and no transcript is persisted or sent elsewhere. The demo retains only the
current session's text, not a searchable history.

## Presentation boundary

The existing Python presentation proposal and all production modules remain
unchanged. The HTML includes its own synthetic model for session identity,
adjacent sequence numbers, transcript revisions, length bounds, and matching
explicit outcomes. It rejects obsolete-session updates and terminal replay.
It is not a replacement accepted kernel-event schema or complete production
transition validator.

The existing Python proposal requires intermediate state transitions; this does
not require that every state get a visible frame. Future integration should
consume authoritative events and coalesce the latest snapshot at rendering
time, preserving the full event semantics. Do not relax safety to fit an
animation. Real partials remain unavailable/unaccepted until the Phase 6 source
can provide them. A production renderer must observe accepted final-only events
correctly without synthesizing purported partials.

## Accessibility and desktop behavior

The prototype provides native buttons, focus indicators, keyboard disclosure,
selectable/scrollable text, a polite status announcement, high-contrast preview,
forced-colors CSS, and reduced-motion behavior. Inert hidden details leave the
tab order. Important states use words and symbols as well as color.

The compact caption is intentionally a secondary glance surface. Essential
decisions and error information use the larger expanded text. A native renderer
must expose accessible names and full transcripts rather than requiring users
to read the tiny caption. It must also verify that essential content fits at
large text scaling.

A normal HTML page cannot demonstrate native click-through, no-activate windows,
global shortcuts, screen-reader integration, actual monitor placement, taskbar
and full-screen rules, or multi-monitor DPI transitions. Production should use
the originating display's usable bounds, avoid taking focus for routine
updates, and make user-invoked inspection/confirmation keyboard reachable.
Confirmation must never intercept an unrelated app's Enter key globally.
Exact native focus and full-screen policies require implementation testing.

## Validation performed

Both embedded JavaScript blocks passed Node syntax checking. Running
`node tests/phase8_seam_checks.cjs` passed **18 behavior checks** covering
explicit outcomes, replay/stale-event rejection, transcript revisions and
bounds, missing final text, quick-state coalescing, preemption, plain mismatch
text, long-text retention, delayed waiting states, pause/resume, confirmation
expiry, error recall, inert disclosure, idle loop cessation, static reduced
motion, and absence of external resources/network/microphone calls.

These checks use a deterministic clock and a small DOM stub. They do not verify
rendered layout, pixels, smoothness, screen readers, resource consumption, or
native Windows behavior. Browser preview was blocked earlier in this chat;
that restriction was respected, and no alternate local browser route was used.
No actual rendered screenshot is claimed.

## Before production acceptance

1. Inspect this selected design at 100%, 125%, 150%, and 200% scaling, including
   a 14-inch laptop, long transcripts, a busy background, keyboard use, high
   contrast, and reduced motion.
2. Validate the real event source: final transcript, explicit outcomes,
   cancellation, confirmation binding/expiry, session supersession, and late
   events. Fix any source ambiguity before connecting the renderer.
3. Compare lightweight native rendering options against the design. No Qt,
   WebView2, or other production rendering framework is selected by this study.
4. Measure first useful frame, command-path overhead, frame pacing, hidden/active
   CPU/RAM, startup, renderer loss, and sustained idle behavior against the
   proposed budgets in `context.md`. HTML timings do not establish those budgets.

No commits, pushes, dependencies, native UI changes, or live-event integration
are part of this refinement. Previous design studies are preserved.
