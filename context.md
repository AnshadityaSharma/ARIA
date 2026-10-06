# ARIA — Authoritative Project Specification

ARIA means **Adaptive Runtime Intelligence Assistant**. This document is the authoritative product and roadmap specification for future ARIA work. Older sprint documents record history and measurements. Where an older plan conflicts with this document, follow this document. Completed work should be verified against new gates, not rewritten merely to match phase order.

## 1. Vision and constraints

ARIA is a local Windows 10/11 assistant for ordinary text and voice computer commands. It should discover installed applications, windows, files, folders, and browser state; perform bounded actions; and verify results. It should feel responsive on ordinary laptops and remain practical to install and run offline after setup.

**Use the simplest mechanism that reliably solves the problem.**

Core requirements are local processing, low latency, low idle RAM and CPU use, modest disk footprint, CPU operation without a dedicated GPU, deterministic execution, safety, clear failures, and extensibility. Audio, transcripts, screenshots, files, clipboard contents, browser data, and private computer state must not leave the device by default. Any cloud feature needs a separate explicit product decision. Keep Windows-specific code isolated without building cross-platform features prematurely.

ARIA is capability-driven. The capability registry defines **what ARIA can do** with typed parameters. Resolvers discover **what exists on the user's machine**. Do not hardcode an application catalogue. An installed game or utility should be launchable through discovery even if ARIA has never seen its name.

A command succeeds only if the intended capability, target, and parameters are interpreted, authorized, executed, and verified where practical. Parsing a sentence is not execution success. Unsupported or ambiguous requests call for abstention or a specific clarification, never a guessed consequential action.

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

The default interpreter is deterministic: normalization, finite capability grammar, quantity and parameter extraction, and explicit reference resolution. It preserves literal payloads, detects negation and compound commands, and abstains if meaning is unclear. For relative geometry, 10% smaller means multiplying observed current dimensions by 0.9; define and test other quantity conventions explicitly.

Keep minimal session state: foreground target captured at activation, last successfully acted-on compatible target, actual and previous window geometry, relevant file/recording/browser references, and pending confirmation. Pronouns require a unique compatible target. If a tracked target vanishes, report that fact rather than substituting a different window or path. Update state from observed outcomes, not proposals.

Prefer native Windows and filesystem APIs. Use DOM and accessibility state for browser actions before visual fallback. Each executor returns a result and observable verification where practical. Prefer reversible operations, including Recycle Bin deletion where possible. Report unavailable applications/devices, ambiguous targets, permissions, timeouts, and verification failures.

## 3. Stable product, experiments, and future work

**Stable product functionality** has passed its functional, safety, performance, and distribution gates. Passing mocks or unit tests alone does not establish stability.

**Experiments** are isolated comparisons against a frozen baseline. They are not release commitments.

**Optional future capabilities** are built only when their gate demonstrates user value at acceptable latency, resource, safety, and distribution cost. Browser expansion, wake word, learned interpretation, and visual fallback are optional until accepted.

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

## 5. Roadmap: Phases 0–11

Phases are logical engineering milestones, not a claim that the repository starts empty. Each can be implemented and verified as a focused increment. Phase 10 is conditional on Phase 7. Phase 11 is separate research. Existing-work mapping appears in Section 10.

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
- **Implement:** Screenshot, volume/mute, and start/stop/save recording through suitable approved local mechanisms; minimal recording state and output verification.
- **Do not implement yet:** Media understanding, visual control, wake word.
- **Prerequisites:** Phases 1–4 and an acceptable recording mechanism.
- **Tests:** Each executor's success/failure, unavailable device, interrupted recording, disk/permission errors, output verification, last-recording reference.
- **Benchmarks:** Incremental startup/idle cost, active RAM/CPU, operation and verification.
- **Acceptance:** Failures are visible and clean; unused utilities add no active background process.
- **Deliverables:** Local utility capabilities.
- **Decision enabled:** Broader text MVP readiness. **Stable milestone:** yes.

### Phase 6 — Voice and activation

- **Objective / why:** Control the same guarded pipeline with local speech.
- **Implement:** Push-to-talk/global hotkey, prompt listening UI, local capture and ASR, transcript/uncertainty/language/timing interface, empty/uncertain rejection, foreground capture at activation.
- **Do not implement yet:** Wake word, second voice parser, LLM.
- **Prerequisites:** Stable text pipeline and approved local ASR.
- **Tests:** Real speakers, Indian English/Hinglish, microphones/noise, ASR substitutions, cancellation, repeated activation, unavailable microphone; synthetic audio only for regression support.
- **Benchmarks:** Hotkey-to-UI, capture/endpointing, ASR cold/warm, transcript-to-action, speech-end-to-result, idle/active resources.
- **Acceptance:** Text and voice use identical policy/execution; uncertain speech cannot cause unintended action; cohorts are reported.
- **Deliverables:** Local voice desktop MVP.
- **Decision enabled:** Full deterministic evaluation. **Stable milestone:** yes after real-speech acceptance.

### Phase 7 — Deterministic interpreter gate

- **Objective / why:** Decide whether learned interpretation is needed at all.
- **Implement:** Freeze held-out set; evaluate capability, target, parameter, abstention, and clarification for typed and real-ASR commands; categorize misses and estimate user frequency. Improve rules on development data only, then rerun held-out evaluation.
- **Do not implement yet:** Install a model merely to explore; rewrite the parser for one example.
- **Prerequisites:** Phase 0 evaluation method, stable declared capabilities from Phases 1–6, and representative samples. Run a scoped baseline on currently implemented capabilities now; repeat the full gate when the declared release command set is complete.
- **Tests:** Negative/unsupported, ambiguity, high-risk targets, code switching, ASR errors, executor and permission regressions.
- **Benchmarks:** Cohort accuracy, false actions, fallback/clarification, p50/p95 latency, voice timing and resources.
- **Acceptance:** Apply Section 6. If passed, stop adding interpreter layers. Otherwise identify the exact failure before choosing a remedy.
- **Deliverables:** Signed-off evaluation and stop / improve rules / test learned interpretation decision.
- **Decision enabled:** Whether Phase 10 is warranted. **Stable milestone:** yes.

### Phase 8 — Bounded browser capabilities

- **Objective / why:** Add verifiable web actions without a browser agent.
- **Implement:** Separate lazy adapter for navigate, search, accessible control identification, type, click, submit, download, and page/file verification; minimal browser/result/download state.
- **Do not implement yet:** Arbitrary JavaScript, visual clicking, autonomous research or page planning.
- **Prerequisites:** Phases 1, 3, and 7; justified browser dependency.
- **Tests:** Deterministic local pages, ambiguous controls, changed page state, failed downloads, page instructions treated as data; separate live smoke tests.
- **Benchmarks:** Package size, cold launch, warm actions, process-tree RAM/CPU, shutdown cleanup and verification.
- **Acceptance:** Browser unloaded for desktop-only commands; all actions use common safety and verification.
- **Deliverables:** Bounded browser capabilities.
- **Decision enabled:** Which web tasks need more reasoning. **Stable milestone:** yes as an optional capability set.

### Phase 9 — Distribution and daily-use reliability

- **Objective / why:** Prove ARIA can run on another Windows computer under normal protections.
- **Implement:** Package text core and justified optional voice/browser components; pin dependencies and notices; installer/update/uninstall, signing/security plan, failure logging and recovery.
- **Do not implement yet:** Bundle unaccepted model or agent.
- **Prerequisites:** Stable core; Phase 6 for voice package and Phase 8 if browser included.
- **Tests:** Clean Windows 10/11 installs, ordinary-user operation, offline run after setup, security enforcement and child binaries, absent devices/apps, update/uninstall, long idle session.
- **Benchmarks:** Download/installed size by component, startup, idle/active RAM/CPU, process count, cold/warm voice and endurance.
- **Acceptance:** Runs without weakening Windows protection; hardware envelope and failure recovery documented.
- **Deliverables:** Candidate daily-use package and hardware report.
- **Decision enabled:** Release scope and supported hardware. **Stable milestone:** yes.

### Phase 10 — Optional learned interpretation experiment

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

### Phase 11 — Optional open-ended task research

- **Objective / why:** Study genuinely multi-step tasks separately from routine commands.
- **Implement:** Bounded task representation, per-step validation and confirmation, checkpoints, interruption and recovery; only then evaluate a local planner/agent on isolated tasks.
- **Do not implement yet:** Unrestricted tools, arbitrary code, vision-first control, agent startup on routine commands.
- **Prerequisites:** Stable daily-use core, bounded browser capabilities where needed, separate safety/resource budgets, approved model/runtime if chosen. Phase 10 is not mandatory.
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

If deterministic interpretation passes, stop. If it fails, first locate the cause: ASR, grammar, slots, discovery, context, or execution. Fix the responsible part. Phase 10 is justified only by valuable remaining language-selection misses.

### Added interpreter

Compare every candidate to the frozen deterministic baseline on the same cases. Require a predeclared complete-action gain, acceptable false actions/abstention, and justified cold/warm latency, RAM, CPU, disk, native-binary, signing, offline, and maintenance cost. Schema-valid output alone is insufficient. A classifier, embedding model, or generative model may all fail; none is mandatory.

### New capability and release

Each executor needs typed validation, target resolution, fixed risk, confirmation where required, target recheck, failure handling, and observed verification. Release additionally requires real-machine, real-voice, offline, clean-install, and normal Windows-security evidence. A development demo is not a completed release.

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

These are not claims about current performance. If real speech or lower-tier hardware differs, record and explicitly revise targets. Track idle/active RAM and CPU, startup, installed and optional-component size, background process count, sustained idle/battery behavior, and GPU dependence. Compare the development laptop with at least one ordinary lower-memory Windows machine before broad claims. Large mandatory checkpoints need exceptional measured value.

Historical numbers in docs/benchmarks.md are configuration-specific observations, not guarantees. Sprint 5's 27-case development corpus intentionally emphasizes misses and rejections; its 37.04% deterministic score does not estimate ordinary-command accuracy.

## 8. Testing methodology

Use four complementary suites:

1. **Unit and contract:** Grammar, typed actions, resolvers, state, policy, confirmation, and every executor's success/failure/cancel paths.
2. **Controlled integration:** Disposable Windows targets and files, deterministic local browser pages, and observed outcomes.
3. **Held-out command evaluation:** Separate from development examples; typed input and consented real human speech covering Indian English, Hinglish, accents, noise, unsupported/ambiguous requests, and ASR errors. Measure complete-action correctness, false actions, abstention, clarification, execution, and verification by cohort.
4. **Distribution and endurance:** Clean install, offline use, Windows security enforcement, restart/shutdown, long idle, and several hardware tiers.

Synthetic audio and live sites are useful smoke checks, not substitutes for real speakers or controlled browser integration. Keep evaluation data local and avoid unnecessary personal content. Separate infrastructure failures from interpretation accuracy.

## 9. Distribution

Start with the smallest text/desktop core. Include voice and browser components with measured size/background costs. Keep any accepted learned interpreter or agent separately installable or loadable and absent from routine startup. Account for runtime, model weights, browser binaries, licenses, child processes, and updates in installed-size reporting.

Test the actual installer/package and every executable/DLL under normal Windows protections. Do not disable, weaken, or bypass Windows Application Control. A blocked runtime remains blocked pending an approved installation. Offline operation is required after explicit setup/provisioning; setup itself may require a download.

## 10. Existing work mapped to the new roadmap

The roadmap does not require rewriting working components. The following mapping reflects the repository at this specification update:

| Treatment | Existing work and phase |
| --- | --- |
| **KEEP** | Typed Action schema, risk table, guarded Engine, confirmation token, target recheck, and timing support Phase 1. Dynamic Start Apps and known-folder discovery, Windows controls, and observed geometry support Phase 2. Explicit tracked-window state and deterministic parser support Phase 3. File and Recycle Bin actions support Phase 4. Screenshot and volume support part of Phase 5. |
| **KEEP; VERIFY AGAINST NEW GATES** | Local push-to-talk ASR, hotkey, overlay, and shared text/voice engine support Phase 6, but real human speech acceptance by cohort is outstanding. Lazy Playwright browser actions and local tests support Phase 8, while distribution cost and broad reliability still need review. |
| **REWORK EVALUATION, NOT WORKING CODE BY DEFAULT** | Phase 0/7 require representative held-out commands beyond Sprint 5's 27-case development set and real-voice evaluation. Existing benchmark tools and logs are foundations. |
| **NOT YET COMPLETE** | Screen recording and its state are absent from the current ActionType list, so part of Phase 5 remains. Phase 7 has not passed. Phase 9 clean-machine/signing acceptance is not established. |
| **OPTIONAL RESEARCH HISTORY** | Sprint 5 Qwen2.5-1.5B/llama.cpp code, mocks, protocol tests, and provisioning notes show one bounded model integration. They do not establish real-model quality or resource suitability and are not the planned/default interpreter. |
| **NOT YET NEEDED** | A complexity router, general agent, wake word, and visual fallback do not block routine-command acceptance. |

Sprint 5's native runtime was blocked by Windows Application Control (WinError 4551). Real-model accuracy, cold/warm latency, loaded RAM/CPU, and smoke acceptance are unmeasured, not passed. The existing instruction not to weaken/bypass protection or try another unapproved runtime remains in force. Do not claim a completed Sprint 5 model release from mocks. The old plan that treated a specific 1.5B model and runtime as the expected fallback is superseded.

## 11. Immediate work and phase sequence

Next, complete Phase 0's representative held-out evaluation and run a scoped Phase 7 deterministic baseline against the existing core. Repeat the full Phase 7 gate after the declared release command set, including any required recording capability, is complete. In parallel, audit package footprint and collect consented real human voice samples. Fix measured discovery, extraction, context, or ASR failures before considering learning. Finish the recording portion of Phase 5 and Phase 9 distribution as focused work without undoing accepted functionality.

Logical sequence:

    0 contract and measurement
    → 1 guarded action kernel
    → 2 dynamic Windows core
    → 3 stateful deterministic language
    → 4 filesystem
    → 5 media and system utilities
    → 6 voice and activation
    → 7 deterministic acceptance gate
       ├─ passes: stop adding interpretation layers
       └─ valuable language-selection misses: consider 10
    → 8 bounded browser capabilities
    → 9 distribution and daily-use release
    → 10 optional learned-interpreter experiment only if Phase 7 warrants it
    → 11 optional separate open-ended task research

Phase numbers indicate scope, not an instruction to redo completed code or to wait until Phase 9 to run an approved Phase 10 experiment after Phase 7. Phase 11 is outside the routine-command release.
