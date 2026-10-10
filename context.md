# ARIA — Authoritative Project Specification

ARIA means **Adaptive Runtime Intelligence Assistant**. This document is the authoritative product and roadmap specification for future ARIA work. Older sprint documents record history and measurements. Where an older plan conflicts with this document, follow this document. Completed work should be verified against new gates, not rewritten merely to match phase order.

## 1. Vision and constraints

ARIA is a local Windows 10/11 assistant for ordinary text and voice computer commands. It should discover installed applications, windows, files, folders, and browser state; perform bounded actions; and verify results. It should feel responsive on ordinary laptops and remain practical to install and run offline after setup.

**Use the simplest mechanism that reliably solves the problem.**

Core requirements are local processing, low latency, low idle RAM and CPU use, modest disk footprint, CPU operation without a dedicated GPU, deterministic execution, safety, clear failures, and extensibility. Audio, transcripts, screenshots, files, clipboard contents, browser data, and private computer state must not leave the device by default. Any cloud feature needs a separate explicit product decision. Keep Windows-specific code isolated without building cross-platform features prematurely.

ARIA is capability-driven. The capability registry defines **what ARIA can do** with typed parameters. Resolvers discover **what exists on the user's machine**. Do not hardcode an application catalogue. An installed game or utility should be launchable through discovery even if ARIA has never seen its name.

A command succeeds only if the intended capability, target, and parameters are interpreted, authorized, executed, and verified where practical. Parsing a sentence is not execution success. Unsupported or ambiguous requests call for abstention or a specific clarification, never a guessed consequential action.

### Product identity and system presence

ARIA's required visual identity is an original **Shard**: a small abstract geometric mark that can also mature into ARIA's logo and application icon. It must not be a generic assistant orb, bubble, waveform sphere, or imitation of Siri, Alexa, Gemini, or another assistant. The rough Shard concept defines a direction rather than a finished design.

ARIA is normally invisible or minimal when idle. On activation, the Shard appears as a polished, lightweight system presence and communicates wake detected, listening, processing, executing, success, error, and confirmation required. It should feel native to Windows without behaving like a conventional application window, stealing focus, covering the active task, or remaining animated unnecessarily.

Before selecting the final design, compare several credible options for shape, silhouette, animation, position, typography, motion language, and color/material treatment. Select through an explicit gate covering uniqueness, recognizability, visual quality, accessibility, resource use, implementation complexity, Windows compatibility, and consistency with ARIA's low-latency philosophy. The Shard is required planned product work and is not complete merely because an engineering overlay already exists.

### Selective local response voice

ARIA will later add an offline, lightweight response voice with a calm, concise, slightly futuristic, and intentional personality. It should not sound overly cheerful, conversational, or verbose. Normal harmless commands should generally remain silent and use the Shard for feedback. Speech is reserved primarily for dangerous or irreversible actions, confirmation requests, important errors, important completion states, and cases where explicit audible feedback materially helps.

The response vocabulary should favor short deterministic messages such as “Confirmation required.”, “Deleting files.”, and “Closing the laptop.” Spoken output never constitutes confirmation and never changes action risk. Do not prescribe a TTS engine yet. Compare local options, including whether a small fixed phrase set is better served without a general synthesizer, using latency, runtime/model size, voice quality, CPU/RAM, Windows compatibility, accessibility, offline behavior, licensing, and maintenance cost. This response-voice layer is planned work, not completed functionality.

## 2. Architecture and safety invariant

Text and locally transcribed voice share one pipeline:

    interpretation
    → typed action
    → validation
    → deterministic risk classification
    → confirmation when required
    → target recheck
    → deterministic execution
    → outcome verification

This invariant applies to every phase and every interpreter. An interpreter may propose a capability and parameters. It cannot execute arbitrary code, choose risk, bypass validation or confirmation, manipulate the OS directly, or arbitrarily access tools. Browser/page content, filenames, documents, and search phrases are data, not instructions. Safety policy addresses the requested action and affected target, not the private content on the machine.

The presentation layer consumes explicit state and outcome events from this pipeline. It cannot authorize an action, infer risk, substitute a target, execute a capability, or turn speech into confirmation. Shard animation and response audio must be nonblocking observers of authoritative kernel state; command execution and verification must never wait for decorative motion or optional speech playback.

The default interpreter is deterministic: normalization, finite capability grammar, quantity and parameter extraction, and explicit reference resolution. It preserves literal payloads, detects negation and compound commands, and abstains if meaning is unclear. For relative geometry, 10% smaller means multiplying observed current dimensions by 0.9; define and test other quantity conventions explicitly.

Keep minimal session state: foreground target captured at activation, last successfully acted-on compatible target, actual and previous window geometry, relevant file/browser references, and pending confirmation. Pronouns require a unique compatible target. If a tracked target vanishes, report that fact rather than substituting a different window or path. Update state from observed outcomes, not proposals.

Prefer native Windows and filesystem APIs. Use DOM and accessibility state for browser actions before visual fallback. Each executor returns a result and observable verification where practical. Prefer reversible operations, including Recycle Bin deletion where possible. Report unavailable applications/devices, ambiguous targets, permissions, timeouts, and verification failures.

## 3. Stable product, experiments, and future work

**Stable product functionality** has passed its functional, safety, performance, and distribution gates. Passing mocks or unit tests alone does not establish stability.

**Experiments** are isolated comparisons against a frozen baseline. They are not release commitments.

**Optional future capabilities** are built only when their gate demonstrates user value at acceptable latency, resource, safety, and distribution cost. Browser expansion, wake word, learned interpretation, and visual control fallback are optional until accepted. The Shard product identity is required planned work; local response voice remains planned behind its technology and policy gate.

**Research/agent work** concerns genuinely open-ended or multi-step tasks. It has a separate budget and gate. Routine commands must never load an agent, planner, vision model, or generative runtime.

Deterministic interpretation is the default and may remain the final routine-command architecture. A classifier, embedding model, small local model, or generative LLM is **not a required destination**. If measured language-selection failures justify learning, test the smallest plausible remedy. First correct rules, extraction, discovery, state, or ASR when those cause the miss. Compare a compact classifier only if appropriate; consider embeddings or constrained generation only when cheaper approaches fail valuable cases. No particular model or runtime is prescribed. The number of layers is determined by measured failures.

Voice is local ASR feeding the same interpretation and execution path. Its interface should expose transcript, available uncertainty/confidence, detected language, and timing. Real human Indian English and Hinglish evaluation is required; synthesized speech alone cannot establish acceptance.

## 4. Development rules

1. Finish and measure a phase before adding a major dependency. Verify and reuse existing components rather than rebuilding them to conform to phase labels.
2. Keep the routine path independent of learned models and open-ended agents. Unused optional components must not create background processes.
3. Add capabilities through typed actions, target resolvers, deterministic risk, guarded executors, and verification. Never enumerate application names in a catalogue.
4. Test each executor's success, failure, cancellation, and consequential-action cases with disposable targets.
5. Report benchmark stage, hardware, sample count, cold/warm state, and percentile. Do not claim unmeasured latency.
6. Keep private data local and minimize diagnostic payload logging.
7. Prefer native APIs over screenshots and DOM/accessibility state over browser vision.
8. Justify every dependency with its latency, RAM, CPU, disk, native-binary, offline, security/signing, installation, and maintenance cost.
9. Never disable, weaken, or bypass Windows security to run a component. An unapproved runtime remains blocked.
10. Clarify or abstain when commands, ASR, or targets are uncertain.

## 5. Roadmap: Phases 0–13

Phases are logical engineering milestones, not a claim that the repository starts empty. Each can be implemented and verified as a focused increment. Phase 12 is conditional on Phase 7. Phase 13 is separate research. Existing-work mapping appears in Section 10.

### Phase 0 — Product contract and measurement foundation

- **Objective / why:** Specify behavior and reproducible evaluation before selecting technology.
- **Implement:** Typed capability/target contract; definitions of complete correctness, false action, abstention, clarification, and verification; stage timing; separate development and held-out examples covering English, Indian English, Hinglish, ASR errors, ambiguity, and unsupported requests.
- **Do not implement yet:** New models, agents, browser reasoning, or unrelated executors.
- **Prerequisites:** Product requirements and consented examples.
- **Tests:** Annotation consistency, metric calculations, duplicate/leakage checks, expected outcomes for ambiguous inputs.
- **Benchmarks:** Baseline startup, idle RAM/CPU, process count, installed size, text interpretation; record hardware.
- **Acceptance:** A second developer can reproduce counts; each case has an explicit expected action, clarification, or abstention.
- **Deliverables:** Versioned contract, corpus, benchmark method, baseline.
- **Decision enabled:** Identify genuine gaps. **Stable milestone:** yes.

### Phase 1 — Typed execution and safety kernel

- **Objective / why:** Establish one authority boundary for every interpreter and executor.
- **Implement:** Capability registry, typed actions/targets, validation, fixed risk metadata, immutable single-use confirmation with timeout, target recheck, executor/result/verification contracts and timing hooks.
- **Do not implement yet:** Broad NLP, voice, browser agent, AI.
- **Prerequisites:** Phase 0 contract.
- **Tests:** Invalid fields/ranges, unsupported action, replay/expiry/cancel, target change, executor and verification failure, bypass attempts.
- **Benchmarks:** Validation and risk time; idle footprint.
- **Acceptance:** No execution path bypasses validation/policy; confirmation cannot authorize a changed target.
- **Deliverables:** Guarded kernel and controlled-adapter tests.
- **Decision enabled:** Safe concrete capabilities. **Stable milestone:** yes.

### Phase 2 — Dynamic Windows discovery and basic control

- **Objective / why:** Prove useful operation without an application catalogue.
- **Implement:** Discover installed applications, foreground/open windows, and known folders; launch, focus, move, resize, minimize, maximize, restore, and open paths through direct text commands; store observed geometry.
- **Do not implement yet:** Learned interpretation, voice, destructive files, browser agent.
- **Prerequisites:** Phase 1.
- **Tests:** Disposable windows, installed/missing/ambiguous apps, vanished targets, multi-monitor/constrained geometry, known folders, observed launch and placement.
- **Benchmarks:** Discovery, startup/idle cost, text-to-action stages, operation and verification times.
- **Acceptance:** Direct commands reliably produce observed results; an installed app not named in tests can be discovered without code changes.
- **Deliverables:** Text-driven Windows core.
- **Decision enabled:** Readiness for natural commands. **Stable milestone:** yes.

### Phase 3 — Stateful deterministic language

- **Objective / why:** Handle everyday phrasing and follow-ups without inference.
- **Implement:** Normalization, capability grammar, quantities/directions/relative changes, literal payload preservation, recent-target state, pronoun rules, clarification/abstention, negation and compound-command handling.
- **Do not implement yet:** Classifier, embeddings, generative fallback, planning.
- **Prerequisites:** Phases 0–2.
- **Tests:** Paraphrases, relative geometry, expired/incompatible references, quoted search text containing command verbs, unsupported and multi-action input, English/Hinglish examples.
- **Benchmarks:** Held-out complete-action accuracy, abstention, false actions, p50/p95 interpretation and state resolution.
- **Acceptance:** Unclear requests cannot silently become different actions; misses are categorized.
- **Deliverables:** Deterministic text interpreter and error report.
- **Decision enabled:** Which language failures remain. **Stable milestone:** yes, even with bounded coverage.

### Phase 4 — Filesystem capabilities

- **Objective / why:** Add useful path operations with consequential-action safety.
- **Implement:** Discover/resolve paths; create, open, copy, move, rename, and Recycle Bin deletion where practical; last-file state, collision behavior, confirmation and identity recheck.
- **Do not implement yet:** Autonomous organization or content understanding.
- **Prerequisites:** Phases 1 and 3.
- **Tests:** Disposable fixtures, missing paths, collisions, permissions, changed target, cancellation, cross-volume move, verification and rollback data.
- **Benchmarks:** Resolution, confirmation display, operation, verification separately.
- **Acceptance:** No destructive action uses an implicit, ambiguous, or changed target; success is verified on disk.
- **Deliverables:** Guarded filesystem control.
- **Decision enabled:** File-operation daily-use readiness. **Stable milestone:** yes.

### Phase 5 — Local media and system utilities

- **Objective / why:** Complete the useful desktop command set without new interpretation architecture.
- **Implement:** Harden existing virtual-desktop screenshot with bound destination, private staging, no overwrite, PNG and geometry verification, and partial-file cleanup. Harden existing set/change volume and mute/unmute with readback of the actual endpoint and truthful failure reporting on device loss or change. Consider only small system utilities that justify their cost. A request to open an existing Windows recorder may use ordinary dynamic application launch if that is sufficient; it does not become an ARIA recording capability.
- **Do not implement:** ARIA-owned screen recording, FFmpeg/ffprobe, recording state/process/verification/dependencies/benchmarks. Defer media understanding, visual control, and wake word beyond this phase.
- **Prerequisites:** Phases 1–4; no recording dependency.
- **Tests:** Screenshot collisions, destination and identity changes, PNG corruption, virtual-desktop dimensions, partial cleanup, permission/disk errors; volume/mute readback, changed/unavailable endpoint, failure; safety-kernel routing.
- **Benchmarks:** Screenshot and audio-operation p50/p95, incremental startup/idle cost, active RAM/CPU, process count, and verification time. No recording benchmark.
- **Acceptance:** Screenshot output is independently verified before success; reported volume/mute reflects observed endpoint state; failures are visible and clean; unused utilities add no active background process or recording dependency.
- **Deliverables:** Verified lightweight local utilities.
- **Decision enabled:** Broader text MVP readiness. **Stable milestone:** yes.

### Phase 6 — Voice, activation, and bounded interaction

- **Objective / why:** Control the same guarded pipeline with local speech.
- **Implement:** Complete and measure push-to-talk/global hotkey, microphone capture, speech onset/endpointing, local ASR, transcript/uncertainty/language/timing, empty/uncertain rejection, and foreground capture at activation. Audit sample format, buffering, overflows, device changes, clipping, pauses, and realistic noise. Preserve one final transcript as the only executable input; expose versioned, display-only partials only if the chosen ASR path can produce useful partials within the measured resource budget. After the voice baseline is sound, add a bounded compound-command increment: deterministic clauses, explicit dependencies, verified result bindings, and safe independent branches. Evaluate physical-cursor and keyboard capabilities as separate typed, guarded, observed actions; add only those whose target/risk/verification contracts can be made safe. Evaluate always-on-top as a bounded window-property extension, not a change to accepted Phase 2 evidence.
- **Do not implement yet:** Wake word, second voice parser, LLM, general workflow engine, visual target guessing, or speculative parallel execution.
- **Prerequisites:** Stable text pipeline and approved local ASR.
- **Tests:** Consented real speakers, Indian English/Hinglish, clean/noisy audio, microphone/device changes, ASR substitutions, cancellation, repeated activation, unavailable microphone, clipped words/pauses, unstable partial revisions, and no execution from partials. For compound actions, independent/dependent/conflicting branches, target identity, confirmation, timeout/cancel, partial failure, and non-idempotent retry prevention. For physical input, distinguish cursor-position actions from visual targeting; verify focus/coordinate binding and fail closed when safety cannot be established. Synthetic audio is regression support only.
- **Benchmarks:** Hotkey-to-UI, onset/endpointing, first useful partial if supported, final ASR cold/warm, transcript-to-action, speech-end-to-verified-result, per-branch wait/critical path, idle/active CPU/RAM/processes, and simple-command regression. Report p50/p95 where sample size permits.
- **Acceptance:** Text and voice use identical policy/execution; uncertain speech and partials cause no unintended action; real-speech cohorts and WER/command correctness are reported separately. Compound work is accepted only after each child passes the kernel and dependent steps consume verified results; independent branches do not race or falsely serialize without a documented safety reason. Physical input and always-on-top ship only after their separate safety/verification gates pass.
- **Deliverables:** Local voice desktop MVP, real-audio evaluation and error report, plus accepted bounded interaction increments if justified.
- **Decision enabled:** Full deterministic evaluation. **Stable milestone:** yes after real-speech acceptance.

### Phase 7 — Deterministic interpreter gate

- **Objective / why:** Decide whether learned interpretation is needed at all.
- **Implement:** Freeze held-out set; evaluate capability, target, parameter, abstention, and clarification for typed and real-ASR commands; categorize misses and estimate user frequency. Improve rules on development data only, then rerun held-out evaluation.
- **Do not implement yet:** Install a model merely to explore; rewrite the parser for one example.
- **Prerequisites:** Phase 0 evaluation method, stable declared capabilities from Phases 1–6, and representative samples. Run a scoped baseline on currently implemented capabilities now; repeat the full gate when the declared release command set is complete. A separately gated Phase 6 increment may be excluded explicitly if it does not pass.
- **Tests:** Negative/unsupported, ambiguity, high-risk targets, code switching, ASR errors, compound dependencies and partial failure for included capabilities, executor and permission regressions.
- **Benchmarks:** Cohort accuracy, false actions, fallback/clarification, p50/p95 latency, voice timing, simple-path regression, and resources.
- **Acceptance:** Apply Section 6. If passed, stop adding interpreter layers. Otherwise identify the exact failure before choosing a remedy.
- **Deliverables:** Signed-off evaluation and stop / improve rules / test learned interpretation decision.
- **Decision enabled:** Whether Phase 12 is warranted. **Stable milestone:** yes.

### Phase 8 — ARIA Shard product identity and system presence

- **Objective / why:** Turn the verified command system into a coherent ARIA product experience before packaging it for daily use.
- **Implement:** First run a design exploration and decision stage with multiple credible Shard concepts. Compare shape/silhouette, animation, position, typography, motion language, and color/material treatment. Include an original compact floating transcript panel that expands on activation and coalesces real, versioned partial text when available, then final text and verified execution states. Then implement the selected lightweight Windows presentation layer for wake detected, listening, processing, executing, success, error, and confirmation required. Use explicit kernel/activation events and accessible confirmation surfaces; keep the Shard normally hidden or minimal.
- **Do not implement yet:** Generic assistant orb/bubble, product dashboard, visual computer control, risk or target decisions in UI code, voice-response/TTS, decorative always-on animation, or a UI-specific execution path.
- **Prerequisites:** Phase 1 event/safety contracts, mature Phase 6 activation and voice-input states, and Phase 7's stable declared routine-command behavior. Exploration may begin earlier, but implementation must use the accepted state contracts.
- **Tests:** Comparative design review; every state and invalid transition; partial revision/final replacement without duplicate execution; long-transcript bounds; rapid/repeated commands; confirmation timeout/cancel; focus stealing and occlusion; taskbar/full-screen behavior; multiple monitors, DPI/scaling, themes, high contrast, reduced motion, keyboard and screen-reader access; renderer/device loss and clean shutdown.
- **Benchmarks:** Kernel-event-to-first-visible-frame, frame pacing, incremental command latency, startup, hidden/active RAM and CPU, GPU dependence, process count, package/asset size, and sustained idle/battery behavior.
- **Acceptance:** The design gate selects an original, recognizable Shard rather than a familiar assistant orb; all states are distinguishable with motion disabled and without color alone; it does not obstruct or unexpectedly focus away from the active application; execution never waits for animation; measured overhead satisfies an approved budget on ordinary Windows hardware.
- **Deliverables:** Design decision record, visual/state specification, accessibility contract, tested Shard presentation layer, and measured resource report.
- **Decision enabled:** Product-identity readiness and whether the selected treatment is suitable for the logo/app icon. **Stable milestone:** yes. **Current status:** planned, not complete.

### Phase 9 — Bounded browser capabilities

- **Objective / why:** Add verifiable web actions without a browser agent.
- **Implement:** Validate the existing separate lazy adapter for navigate, search, accessible control identification, type, click, submit, download, and page/file verification; minimal browser/result/download state. Add only bounded, explicit multi-step browser recipes that the Phase 6 coordinator can safely express. Evaluate reuse of authenticated sessions without reading or logging credentials; do not promise reuse of an unrelated browser profile.
- **Do not implement yet:** Arbitrary JavaScript, visual clicking, autonomous research or page planning.
- **Prerequisites:** Phases 1, 3, and 7; justified browser dependency. The browser adapter may emit Phase 8 presentation events but cannot depend on UI for safety or execution.
- **Tests:** Deterministic local pages, ambiguous controls, changed page state, failed downloads, session loss/reuse, auth-required pages without credential collection, partial workflow failure, page instructions treated as data; separate live smoke tests.
- **Benchmarks:** Package size, cold launch, warm actions, process-tree RAM/CPU, shutdown cleanup and verification.
- **Acceptance:** Browser unloaded for desktop-only commands; all actions use common safety and verification.
- **Deliverables:** Bounded browser capabilities.
- **Decision enabled:** Which web tasks need more reasoning. **Stable milestone:** yes as an optional capability set.

### Phase 10 — Selective local response voice

- **Objective / why:** Add concise audible feedback where silence or visual feedback alone is insufficient, without turning ARIA into a conversational persona.
- **Implement:** Begin with a technology and policy evaluation rather than a predetermined TTS engine. Compare deterministic fixed/local phrase approaches and suitable offline synthesis options. Implement the smallest accepted local system for dangerous/irreversible actions, confirmation requests, important errors, important completion states, and other explicitly approved cases. Define interruption, queuing, cancellation, mute, volume, audio-device failure, and Shard synchronization behavior.
- **Do not implement yet:** Cloud speech, generative dialogue, open-ended narration, constant spoken acknowledgements, a second command interpreter, spoken authorization, or speech that blocks execution/verification.
- **Prerequisites:** Accepted Phase 6 voice input/activation interfaces, Phase 7 routine-command vocabulary, and Phase 8 presentation/event semantics. Wake-word behavior is not required, but if wake word is pursued its activation interface must be stable before wake-specific response behavior ships.
- **Tests:** Silent harmless-command policy; exact dangerous/confirmation/error/completion phrase selection; no speech treated as confirmation; rapid and overlapping events; cancel/interruption; unavailable or changed audio device; mute; offline operation; pronunciation/intelligibility and personality review with real listeners; accessibility interaction.
- **Benchmarks:** Event-to-audio-onset cold/warm p50/p95, synthesis duration versus playback, incremental command latency, idle/active RAM and CPU, process count, model/runtime and installed size, and long-idle behavior.
- **Acceptance:** The technology gate selects an offline option with justified quality/resource tradeoffs; normal harmless commands remain silent by default; required messages are concise and intelligible; the voice sounds calm, intentional, and restrained; unavailable speech degrades to accessible Shard/text feedback; command execution and confirmation creation do not wait for audio.
- **Deliverables:** Technology decision record, response policy/vocabulary, local audio implementation, listener evaluation, and resource report.
- **Decision enabled:** Whether response voice belongs in the default package or an optional local component. **Stable milestone:** yes after acceptance. **Current status:** planned, not complete.

### Phase 11 — Distribution and daily-use reliability

- **Objective / why:** Prove the complete ARIA experience can run on another Windows computer under normal protections.
- **Implement:** Package the text core and required Phase 8 Shard, plus justified optional voice-input, response-voice, and browser components; pin dependencies and notices; installer/update/uninstall, signing/security plan, failure logging and recovery.
- **Do not implement yet:** Bundle an unaccepted model, TTS runtime, browser, or agent.
- **Prerequisites:** Stable core and accepted Phase 8 Shard; Phase 6 for voice-input packaging, Phase 9 if browser is included, and Phase 10 if response voice is included.
- **Tests:** Clean Windows 10/11 installs, ordinary-user operation, offline run after setup, security enforcement and child binaries, absent devices/apps, update/uninstall, Shard behavior under real desktop conditions, optional-component isolation, and long idle session.
- **Benchmarks:** Download/installed size by component, startup, idle/active RAM/CPU, process count, Shard overhead, cold/warm voice, and endurance.
- **Acceptance:** Runs without weakening Windows protection; the actual Shard-based experience passes daily-use testing; optional components remain absent from routine startup when not installed or enabled; hardware envelope and failure recovery are documented.
- **Deliverables:** Candidate daily-use package and hardware report.
- **Decision enabled:** Release scope and supported hardware. **Stable milestone:** yes.

### Phase 12 — Optional learned interpretation experiment

Only enter this phase if Phase 7 finds valuable unresolved language-selection misses.

- **Objective / why:** Recover measured misses with the smallest justified interpreter.
- **Implement:** Compare compact supervised capability classification plus deterministic slot extraction and explicit UNKNOWN when appropriate. If inadequate, compare embeddings; consider constrained small generation only with evidence. Every candidate feeds the existing typed-action gate.
- **Do not implement yet:** Multiple shipped models, general planning, model risk selection, direct executor access.
- **Prerequisites:** Phase 7 failure analysis, representative data, resource budget, approved runtime for any native component.
- **Tests:** Frozen held-out and fresh cases, open-set requests, disagreements, negation, payload verbs, wrong targets, runtime unavailability/timeout, policy non-bypass.
- **Benchmarks:** Incremental complete-action gains and false actions, fallback frequency, cold/warm latency, RAM/CPU, package size, native-binary count.
- **Acceptance:** Predeclared valuable gain without safety or resource-budget regression; otherwise ship no learned interpreter.
- **Deliverables:** Comparative evidence and ship one / revise / ship none decision.
- **Decision enabled:** Whether learning becomes optional product functionality. **Stable milestone:** only after acceptance.

### Phase 13 — Optional open-ended task research

- **Objective / why:** Study genuinely multi-step tasks separately from routine commands.
- **Implement:** Bounded task representation, per-step validation and confirmation, checkpoints, interruption and recovery; only then evaluate a local planner/agent on isolated tasks.
- **Do not implement yet:** Unrestricted tools, arbitrary code, vision-first control, agent startup on routine commands.
- **Prerequisites:** Stable daily-use core, bounded browser capabilities where needed, separate safety/resource budgets, approved model/runtime if chosen. Phase 12 is not mandatory.
- **Tests:** Partial failures, changing pages, misleading content, cancellation, repeated confirmation, recovery, resource exhaustion, no direct model-to-OS route.
- **Benchmarks:** Verified task/step success, false actions, completion/recovery time, RAM/CPU, installed size.
- **Acceptance:** Separate safety and reliability gate passes; otherwise retain research only.
- **Deliverables:** Isolated prototype or decision not to ship.
- **Decision enabled:** Whether open-ended work becomes optional product functionality. **Stable milestone:** only after acceptance.

## 6. Decision gates

### Deterministic interpretation

Measure **complete correctness**: capability, target, parameters, and the correct decision to act, clarify, or abstain. Report selective accuracy and coverage together for typed input, real ASR transcripts, English, Indian English, and Hinglish. Report unsupported/ambiguous inputs separately.

Proposed initial daily-use thresholds for declared supported, unambiguous commands:

- At least 95% complete correctness for typed commands and 90% for real voice transcripts in each declared supported cohort.
- Zero unintended high-risk executions in the gate suite; 100% of high-risk attempts use confirmation and target recheck.
- Low-risk false-action rate below 0.5% on a substantial negative/ambiguous set, with sample size and uncertainty reported.
- Clarification and abstention frequencies disclosed by capability; abstaining on everything is not success.

These are **proposed targets to validate, not existing measurements or guarantees**. Zero observed failures in a small suite does not establish zero field risk. Expand the held-out set before broad distribution. A failing language cohort remains experimental rather than being hidden in an overall score.

If deterministic interpretation passes, stop. If it fails, first locate the cause: ASR, grammar, slots, discovery, context, or execution. Fix the responsible part. Phase 12 is justified only by valuable remaining language-selection misses.

### Voice excellence and bounded interaction gate

Before changing ASR settings or models, freeze a consented local real-audio development/regression set and a separate held-out set. Establish the current 16 kHz mono capture and CPU `int8` multilingual `base` baseline on target Windows hardware. Report transcript WER where meaningful, exact command intent, target and parameter correctness, false activations, missed commands, false actions, first useful partial (or explicitly unavailable), finalization, speech-end-to-verified-result, and CPU/RAM. Split results by speaker/accent, English/Hinglish, noise, microphone, command length, and parameter type. Attribute misses to capture, endpointing, ASR, normalization, interpretation, resolution, policy, or execution before changing a component. Set numeric accuracy and resource acceptance thresholds from the baseline and declared hardware envelope, then compare candidates on the same frozen cases; do not claim improvement from a synthetic-only or single-utterance run. Raw microphone audio is not retained by default for evaluation.

For bounded multi-action requests, a small explicit dependency graph is eligible only after the single-action voice path is reliable. Every node is a typed Action passed separately through the authoritative kernel. No dependent node starts until its prerequisite has a verified outcome and bound target; no risk or target decision comes from the coordinator or UI. Independent launches may overlap only after launch admission, unique window correlation, confirmation state, tracked-target writes, and cancellation are safely isolated. Otherwise keep them serialized and report the reason. This extends the accepted Phase 3 compound-command rejection; it does not retroactively change Phase 3 acceptance. Physical cursor actions and keyboard input need separate target/focus, risk, recheck, and verification contracts before inclusion; an OS input call alone cannot prove the intended application effect.

### Shard design and implementation

The Phase 8 design gate must compare several materially different concepts rather than polishing the first sketch. Record visual examples and a scored rationale for shape/silhouette, state motion, position, typography, color/material treatment, and logo/icon suitability. Review with motion enabled and disabled, at common Windows scaling levels, in light/dark/high-contrast conditions, and over representative applications.

Selection criteria are uniqueness, recognizability, visual quality, accessibility, low resource use, implementation complexity, Windows compatibility, and consistency with low latency. Any concept that reads as a familiar assistant orb/bubble, relies on color alone, steals focus, obscures work, or requires a heavy always-running renderer fails. Visual preference alone is insufficient: prototype finalists must have measured startup, event-to-first-frame, idle/active RAM and CPU, GPU behavior, package size, and command-latency impact.

Initial proposed Phase 8 budgets, to validate rather than treat as guarantees, are: p95 under 50 ms from activation/event receipt to the first useful frame; no more than 5 ms p95 added to the guarded command path; hidden idle CPU no more than 0.1% of one logical core above the non-UI baseline; incremental hidden working set no more than 20 MiB; incremental active working set no more than 30 MiB; and no dedicated-GPU requirement. Animation must stop when hidden. Revise a budget only with measured evidence and an explicit product decision.

### Response voice technology and policy

The Phase 10 gate first determines whether the approved finite response vocabulary needs general synthesis at all. Compare the smallest credible offline approaches on real Windows hardware and with real listeners. Report audio onset cold/warm, quality and intelligibility, personality fit, installed/runtime size, active and idle RAM/CPU, process behavior, Windows compatibility/security, licensing, and offline operation. A pleasant voice that materially harms responsiveness or package size can fail; a tiny voice that users cannot understand can also fail.

Initial proposed Phase 10 budgets, subject to evidence, are: p95 warm event-to-audio onset under 300 ms and cold onset under 1 s for short messages; no more than 5 ms p95 added to the guarded command path; zero synthesizer CPU use while silent; no mandatory resident synthesis process; incremental active working set no more than 100 MiB; and installed response-voice assets/runtime no more than 100 MiB. These are validation targets, not current facts. A larger component requires clear measured value and may remain optional.

The policy gate reviews every spoken-event category. Harmless successful commands are silent by default. Confirmation, risk, and execution state come only from the kernel. Spoken wording must be short, deterministic, non-sensitive by default, interruptible, and backed by equivalent accessible visual/text feedback. Speech playback or recognition of the spoken output cannot approve an action.

### Added interpreter

Compare every candidate to the frozen deterministic baseline on the same cases. Require a predeclared complete-action gain, acceptable false actions/abstention, and justified cold/warm latency, RAM, CPU, disk, native-binary, signing, offline, and maintenance cost. Schema-valid output alone is insufficient. A classifier, embedding model, or generative model may all fail; none is mandatory.

### New capability and release

Each executor needs typed validation, target resolution, fixed risk, confirmation where required, target recheck, failure handling, and observed verification. Release additionally requires real-machine, real-voice, Shard product-experience, offline, clean-install, and normal Windows-security evidence. A development demo or engineering overlay is not a completed release.

## 7. Performance and resource methodology

Track command recognition, interpretation, risk decision, execution, verification, complete text latency, voice capture/endpointing, ASR, and speech-end-to-verified-result separately. Report p50/p95 across repeated warm runs and separate cold runs, with hardware, OS, sample count, and timeout. Report app launches, browser navigation, and network work by target rather than promising one global duration.

Initial **proposed targets, subject to measurement**:

| Measure | Proposed target |
| --- | --- |
| Hotkey to visible listening UI | p95 under 50 ms |
| Clear text to deterministic interpretation | p95 under 20 ms |
| Clear text to validated action/risk decision | p95 under 50 ms |
| Native move/focus to verified result | p95 under 500 ms; constrained resize separately |
| Short speech end to transcript on development laptop | initial p95 at most 2.5 s |
| Short speech end to verified native move/focus | initial p95 at most 3 s |
| Shard event to first useful frame | initial p95 under 50 ms |
| Shard contribution to guarded command path | initial p95 no more than 5 ms |
| Warm response event to audio onset | initial p95 under 300 ms |
| Cold response event to audio onset | initial p95 under 1 s |
| Response-voice contribution to guarded command path | initial p95 no more than 5 ms |

These are not claims about current performance. If real speech or lower-tier hardware differs, record and explicitly revise targets. Track idle/active RAM and CPU, startup, installed and optional-component size, background process count, sustained idle/battery behavior, and GPU dependence. Measure the Shard hidden, animating, and under rapid state transitions; measure response voice silent, cold, warm, synthesizing, and playing. Compare the development laptop with at least one ordinary lower-memory Windows machine before broad claims. Large mandatory checkpoints need exceptional measured value.

Historical numbers in docs/benchmarks.md are configuration-specific observations, not guarantees. Sprint 5's 27-case development corpus intentionally emphasizes misses and rejections; its 37.04% deterministic score does not estimate ordinary-command accuracy.

## 8. Testing methodology

Use five complementary suites:

1. **Unit and contract:** Grammar, typed actions, resolvers, state, policy, confirmation, and every executor's success/failure/cancel paths.
2. **Controlled integration:** Disposable Windows targets and files, deterministic local browser pages, and observed outcomes.
3. **Held-out command evaluation:** Separate from development examples; typed input and consented real human speech covering Indian English, Hinglish, accents, noise, unsupported/ambiguous requests, and ASR errors. Measure complete-action correctness, false actions, abstention, clarification, execution, and verification by cohort.
4. **Product experience and accessibility:** Shard state recognition, focus/occlusion, multiple monitors and scaling, themes/high contrast/reduced motion, keyboard/screen-reader confirmation, real-listener response-voice quality, silent-command policy, audio interruption/device failure, and measured UI/audio overhead.
5. **Distribution and endurance:** Clean install, offline use, Windows security enforcement, restart/shutdown, long idle, and several hardware tiers using the actual Shard-based experience and any included local voice components.

Synthetic audio and live sites are useful smoke checks, not substitutes for real speakers or controlled browser integration. Keep evaluation data local and avoid unnecessary personal content. Separate infrastructure failures from interpretation accuracy.

## 9. Distribution

Start with the smallest text/desktop core. The accepted Shard is part of the product experience but must retain its measured lightweight hidden state. Include voice input, response voice, and browser components only with measured size/background costs and the packaging decision from their gates. Keep any accepted learned interpreter or agent separately installable or loadable and absent from routine startup. Account for UI assets/rendering runtime, speech runtime or phrase assets, model weights, browser binaries, licenses, child processes, and updates in installed-size reporting.

Test the actual installer/package and every executable/DLL under normal Windows protections. Do not disable, weaken, or bypass Windows Application Control. A blocked runtime remains blocked pending an approved installation. Offline operation is required after explicit setup/provisioning; setup itself may require a download.

## 10. Existing work mapped to the new roadmap

The roadmap does not require rewriting working components. The following mapping reflects the repository at this specification update:

| Treatment | Existing work and phase |
| --- | --- |
| **KEEP** | Typed Action schema, risk table, guarded Engine, confirmation token, target recheck, and timing support Phase 1. Dynamic Start Apps and known-folder discovery, Windows controls, and observed geometry support Phase 2. Explicit tracked-window state and deterministic parser support Phase 3. File and Recycle Bin actions support Phase 4. Verified screenshot and audio readback support Phase 5, accepted with documented native-environment limits. These contracts can emit presentation events without moving safety decisions into the UI. |
| **KEEP; VERIFY AGAINST NEW GATES** | Local push-to-talk ASR, hotkey, overlay, and shared text/voice engine support Phase 6, but real human speech acceptance by cohort is outstanding. The existing overlay is an engineering surface, not an accepted Shard design. Lazy Playwright browser actions and local tests support Phase 9, while distribution cost and broad reliability still need review. |
| **REWORK EVALUATION, NOT WORKING CODE BY DEFAULT** | Phase 0/7 require representative held-out commands beyond Sprint 5's 27-case development set and real-voice evaluation. Existing benchmark tools and logs are foundations. |
| **ACCEPTED WITH LIMITATIONS** | Phase 5 screenshot and audio readback hardening passed its scoped gate. The native-environment limits in [docs/phase5-media.md](docs/phase5-media.md) remain: deliberate changed-level/mute transitions, Windows 10, physical multi-monitor capture, and device-loss behavior on hardware have not been verified. |
| **NOT YET COMPLETE** | Phase 6 real-human voice acceptance, partial-display feasibility, bounded compound scheduling, and separately gated physical input/window-property extensions are unaccepted. Phase 7 has not passed. Phase 8 Shard exploration/selection/implementation and Phase 10 local response voice have not begun. Phase 11 clean-machine/signing acceptance is not established. |
| **OPTIONAL RESEARCH HISTORY** | Sprint 5 Qwen2.5-1.5B/llama.cpp code, mocks, protocol tests, and provisioning notes show one bounded model integration. They do not establish real-model quality or resource suitability and are not the planned/default interpreter. |
| **OUT OF SCOPE / NOT YET NEEDED** | ARIA-owned recording and recording dependencies are excluded by product decision. A complexity router, general agent, wake word, and visual control fallback do not block routine-command acceptance. The required Shard is a presentation layer, not visual-control inference. |

Sprint 5's native runtime was blocked by Windows Application Control (WinError 4551). Real-model accuracy, cold/warm latency, loaded RAM/CPU, and smoke acceptance are unmeasured, not passed. The existing instruction not to weaken/bypass protection or try another unapproved runtime remains in force. Do not claim a completed Sprint 5 model release from mocks. The old plan that treated a specific 1.5B model and runtime as the expected fallback is superseded.

## 11. Immediate work and phase sequence

Phases 0–4 are accepted and should not be rebuilt. Phase 5 screenshot and audio readback hardening is accepted with documented limitations; see [docs/phase5-media.md](docs/phase5-media.md). Changed-state audio and wider Windows geometry checks remain useful compatibility work, not prerequisites for this scoped gate. The unchanged Phase 6 voice path now has an execution-free replay harness, an opt-in no-execution live-trial seam, and a synthetic smoke, but no representative consented human-audio baseline; its gate remains open (see [docs/phase6-voice-baseline.md](docs/phase6-voice-baseline.md) and [docs/phase6-corpus-protocol.md](docs/phase6-corpus-protocol.md)). Collect and freeze that baseline before prioritizing capture/endpointing/ASR fixes or changing settings. Gate bounded compound scheduling and physical input separately. Run the Phase 7 deterministic gate on the declared accepted command set. Fix measured discovery, extraction, context, or ASR failures before considering learning. The requirement coverage and practical scenarios are in [docs/roadmap-audit.md](docs/roadmap-audit.md).

Do not implement the Shard or response voice during Phase 5. Phase 8 design research can collect references and define comparison methods while Phase 6/7 mature, but final implementation must use the accepted activation, safety, and outcome-event contracts. Build and test the Shard before Phase 11 distribution so daily-use evaluation exercises the intended ARIA experience. Evaluate local response voice in Phase 10 only after voice input and activation are mature enough to judge timing, overlap, personality, and fallback behavior. Neither phase requires redesigning accepted Phases 0–4; they require a narrow, nonblocking presentation-event interface if the current hooks are insufficient.

Logical sequence:

    0 contract and measurement
    → 1 guarded action kernel
    → 2 dynamic Windows core
    → 3 stateful deterministic language
    → 4 filesystem
    → 5 media and system utilities
    → 6 voice, activation, and bounded interaction
    → 7 deterministic acceptance gate
       ├─ passes: stop adding interpretation layers
       └─ valuable language-selection misses: consider 12
    → 8 ARIA Shard product identity and system presence
    → 9 bounded browser capabilities
    → 10 selective local response voice
    → 11 distribution and daily-use release
    → 12 optional learned-interpreter experiment only if Phase 7 warrants it
    → 13 optional separate open-ended task research

Phase numbers indicate scope, not an instruction to redo completed code or to wait until Phase 11 to run an approved Phase 12 experiment after Phase 7. Phase 13 is outside the routine-command release. Phase 9 browser work is an optional capability set and need not block Phase 10/11 when excluded from the chosen release scope.
