# Security boundary

Every action has explicit deterministic risk metadata. Unknown actions/fields and
malformed parameters are denied. NONE/LOW are allowed by default; MEDIUM/HIGH require
confirmation. `--confirm-low` optionally includes LOW.

The old `confirmed=True` bypass is removed. Confirmations bind an immutable validated
action to resolved absolute paths. Tokens are scoped to one engine, single-use, and
expire after a configurable 30 seconds. Cancel, timeout, duplicate clicks, and stale
requests execute nothing. Changed file identity/size/modification time requires a
fresh request. Existing destinations are refused. Delete uses the Recycle Bin.

The trusted UI/controller invokes approval; parsers only produce actions. Arbitrary
Python running in the same process already has OS privileges and is outside this
boundary. File rechecks are not transactional locks against concurrent external edits.

Audio stays in memory; there is no idle microphone loop. Interactive ASR uses cached
local weights only. Weight provisioning is an explicit setup download, not remote
inference. Local diagnostics contain action metadata, file paths, timings, and errors.

Browser URLs are limited to HTTP(S) and embedded credentials are rejected. General
browser actions use accessible names/roles and never accept arbitrary JavaScript or
CSS selectors. General clicks and downloads are LOW risk; submit is MEDIUM and binds
the exact immutable action, page, accessible node, markup, and current form values to
a single-use confirmation. Changed or unbindable targets fail closed. Downloads refuse
overwrite and observe the saved file; content verification remains explicit and
unverified. This is not a sandbox against a malicious website, and
ARIA does not enter passwords or implement purchase, messaging, email, or account
change workflows in Phase 6.

Executor acknowledgment, an observed result, and verified success are distinct. The
current per-capability status and kernel timing method are documented in
`docs/phase1-safety-kernel.md` and `docs/phase1-baseline.md`.
