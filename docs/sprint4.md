# Sprint 4

Scope: Phase 6 deterministic browser automation through Playwright. The browser
capability remains separate from Windows desktop automation and is reached through
the existing validated action, permission, execution, voice, and hotkey pipeline.

## Design

- Playwright and Chromium load lazily on the first browser action. ARIA startup,
  desktop commands, and local ASR do not launch a browser process.
- One browser, context, and active page persist across sequential commands. State
  records the current URL, last search, and last saved download.
- Open website may create a session. Stateful navigation, click, type, submit,
  playback, and download commands require the existing page; a closed page yields
  a clear open-browser recovery instruction.
- URLs permit only HTTP(S), reject embedded credentials, and are normalized before
  permission evaluation/execution. Only YouTube, Google, and GitHub have convenience
  aliases; arbitrary valid sites remain dynamically addressable.
- User-facing labels and accessibility roles drive general interactions. ARIA does
  not accept arbitrary JavaScript or user-provided CSS selectors.
- YouTube result selection reads accessible links, scores titles deterministically,
  follows a watch link, and verifies a video element. It does not use screenshots.
- Downloads use Playwright's download event, are saved through a resolved local
  destination without overwrite, verified on disk, and recorded in browser state.
- Explicit startup, navigation, element, and download timeouts are configurable in
  BrowserConfig. Engine/controller shutdown closes browser resources.

## Safety and exclusions

Opening, navigation, search, typing, and YouTube playback are NONE risk; general
clicks and downloads are LOW; form submission is MEDIUM and therefore needs
confirmation. No email/message sending, purchases, account changes, arbitrary
scripts, LLM, browser agent, vision model, cloud speech API, or wake-word system was
added.

Generic DOM workflows necessarily depend on the site's accessibility contract.
YouTube is the most fragile path: consent pages, bot checks, regional variations, or
markup changes can prevent result discovery. Those failures are reported separately
from local deterministic browser failures.

## Verification

tests/test_browser.py covers action validation, parser mapping, URL policy, risk,
lazy initialization, state loss, reuse, cleanup, and timeout bounds. The opt-in local
integration suite launches real Chromium against a deterministic loopback site and
tests navigation, accessible type/click/submit, confirmed submission, download
verification, state updates, lost-page handling, and close.

The live YouTube smoke is separately marked external_browser because internet/site
behavior is not deterministic. Automated voice acceptance uses synthesized speech;
a human speaking into the microphone remains a manual acceptance check.

Verification on 2026-09-22/23: the unit and real local Chromium suites passed. The
separately gated live YouTube smoke reached and played a matching result in successful
runs. Repeated runs also observed variable ad/media delivery that reached the correct
watch page but remained paused; that exact external condition is reported as xfail,
while local workflow, result-selection, or navigation failures remain hard failures.
The final all-phase real-machine run passed all 88 tests with five existing
sounddevice/NumPy deprecation warnings. See benchmarks.md for measured latency and
resource figures.
