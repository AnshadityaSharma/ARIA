# ARIA — Adaptive Runtime Intelligence Assistant

## 1. Project Overview

ARIA stands for:

**Adaptive Runtime Intelligence Assistant**

ARIA is a **local-first, low-latency voice-controlled computer automation system**.

The goal is not to build another cloud-based AI agent that sends every user request to a large language model, reasons over it, calls tools repeatedly, observes screenshots, and eventually performs an action.

The goal is to build a computer assistant that can perform ordinary computer tasks **almost immediately**, using deterministic local APIs and lightweight local intelligence whenever possible.

Examples:

- "ARIA, open Camera."
- "ARIA, open Chrome."
- "ARIA, make this window one-fifth of the screen and move it to the top right."
- "Make it 10% smaller."
- "Start screen recording."
- "Save that recording to the Videos folder."
- "Open YouTube and play Blinding Lights."
- "Create a folder called ARIA on my desktop."
- "Open VS Code."
- "Make this window louder." / "Increase the volume."
- "Move this window slightly to the left."

More complex tasks can eventually use a local AI planner/agent, but simple tasks must NOT unnecessarily invoke a heavyweight model.

The central design principle is:

> **Use the minimum amount of computation and intelligence necessary to correctly execute each task.**

ARIA should feel like a native computer capability rather than a chatbot controlling a computer.

---

# 2. Product Philosophy

ARIA has five primary principles:

### 2.1 Local-first

Core functionality should execute locally.

User audio, screenshots, files, browser information, commands, and computer state should not be sent to a cloud service unless the user explicitly enables a cloud-based feature.

ARIA should be useful without an internet connection for its core desktop automation functionality.

---

### 2.2 Latency-first

Simple commands should execute with extremely low latency.

For example:

> "Open Notepad."

should not involve:

```text
audio
→ cloud API
→ LLM
→ tool selection
→ cloud response
→ computer action
```

Instead:

```text
audio
→ local speech recognition
→ intent
→ deterministic action
→ Windows API
```

The actual execution path should be as short as possible.

---

### 2.3 Deterministic execution

AI should primarily interpret commands.

AI should NOT directly control the computer through arbitrary code.

Preferred architecture:

```text
Natural language
        ↓
Intent / structured action
        ↓
Validation
        ↓
Risk policy
        ↓
Deterministic executor
        ↓
Operating system / browser / filesystem
```

The executor should be responsible for what actually happens.

---

### 2.4 Stateful interaction

ARIA must understand short-term conversational context.

Example:

User:

> "Make the Camera window one-fifth of the screen and put it in the top right."

ARIA performs it.

User:

> "Make it 10% smaller."

ARIA must understand that "it" refers to the Camera window and that "10% smaller" is relative to the current state.

This should initially be implemented using explicit session state, NOT an LLM.

---

### 2.5 Safety without unnecessary content restrictions

ARIA is a local computer automation tool.

ARIA should not unnecessarily inspect, censor, classify, or refuse ordinary actions because private, sensitive, or adult content happens to exist on the user's computer.

For example, if a user's Downloads folder contains NSFW/private files, ARIA should still be able to:

- open Downloads
- move files
- rename files
- organize files
- search for files

The safety system should focus on **what action ARIA is about to perform**, not on judging the content of the user's computer.

High-impact actions should require explicit user confirmation.

---

# 3. Primary Goal

Build a Windows-first prototype that can:

1. Listen locally for a voice command.
2. Convert speech to text locally.
3. Understand common commands with minimal computation.
4. Convert commands into structured actions.
5. Execute those actions through native/local APIs.
6. Maintain short-term state for follow-up commands.
7. Detect actions that require confirmation.
8. Ask for confirmation before high-impact actions.
9. Measure latency and resource usage.
10. Eventually fall back to a local AI agent for complex tasks.

---

# 4. Initial Target Platform

## Version 1

**Windows 10/11**

The developer's primary development machine is:

- Dell Precision 5550
- 32 GB RAM
- 512 GB SSD
- Intel 10th-generation processor

The first implementation should optimize for Windows.

Cross-platform support should NOT be a priority during the initial implementation.

---

# 5. High-Level Architecture

```text
                         ┌────────────────────┐
                         │       ARIA         │
                         │ Adaptive Runtime   │
                         │ Intelligence       │
                         │ Assistant          │
                         └─────────┬──────────┘
                                   │
                         Voice / Text Input
                                   │
                                   ▼
                        ┌────────────────────┐
                        │  Local Speech      │
                        │  Recognition       │
                        └─────────┬──────────┘
                                  │
                                  ▼
                        ┌────────────────────┐
                        │ Intent / Command   │
                        │ Router             │
                        └─────────┬──────────┘
                                  │
                     ┌────────────┴────────────┐
                     │ Complexity / Capability │
                     │ Router                  │
                     └────────────┬────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
        FAST PATH            SMART PATH          AGENT PATH
              │                   │                   │
       Rules / APIs         Tiny local model      Local LLM
              │                   │                   │
              ▼                   ▼                   ▼
       Native Windows       Structured actions   Planner + UI
       APIs / filesystem    / browser actions    inspection
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                                  ▼
                         ┌────────────────────┐
                         │ Action Validator   │
                         └─────────┬──────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │ Risk / Permission  │
                         │ Engine             │
                         └─────────┬──────────┘
                                   │
                        ┌──────────┴──────────┐
                        │                     │
                    Low Risk              High Risk
                        │                     │
                        ▼                     ▼
                    Execute             Ask User
                                              │
                                       Confirm / Cancel
                                              │
                                              ▼
                                           Execute
```

---

# 6. The Three Execution Paths

ARIA should have three progressively more expensive execution paths.

## PATH 1 — FAST PATH

For deterministic/common commands.

Examples:

- Open application
- Close application
- Resize window
- Move window
- Minimize/maximize window
- Open folder
- Create folder
- Open file
- Start/stop recording
- Volume controls
- Mute/unmute
- Take screenshot
- Launch website
- Basic filesystem operations

These should preferably require:

**no LLM.**

Possible processing:

```text
ASR
→ command matching
→ structured action
→ executor
```

---

## PATH 2 — SMART PATH

For natural-language commands that are still structured but harder to parse.

Examples:

> "Make the window about one fifth of the screen."

> "Move this to the upper-right and make it a little smaller."

> "Open YouTube and search for the Interstellar soundtrack."

A small local language model may convert the command into a strict action schema.

Example:

```json
{
  "action": "RESIZE_WINDOW",
  "target": "active_window",
  "width_ratio": 0.20,
  "position": "TOP_RIGHT"
}
```

The model does not execute the action.

ARIA's deterministic executor does.

---

## PATH 3 — AGENT PATH

For genuinely complex tasks.

Example:

> "Open Gemini, ask it to research why tigers are endangered, create a document from the answer, download it and save it in my Documents folder."

This may require:

- browser automation
- webpage interaction
- waiting
- state observation
- document handling
- file management
- recovery from failures

A local LLM/agent can be used here.

This path is allowed to be slower.

The important goal is that simple tasks never pay the latency cost of this path.

---

# 7. Voice Interface

Initial interaction should support a global hotkey.

Example:

```text
Ctrl + Space
```

The user presses the hotkey and speaks.

Later, support:

> "Hey ARIA..."

using a lightweight local wake-word detector.

The UI itself should be minimal.

Possible design:

```text
┌──────────────────────────────────────┐
│  ● ARIA                              │
│                                      │
│  Listening...                        │
└──────────────────────────────────────┘
```

The visual interface is not a primary feature initially.

Latency and execution correctness are more important.

---

# 8. Speech Recognition Requirements

Speech recognition must run locally.

It should support:

- English
- Indian English
- reasonable accents
- natural speech
- short commands
- mixed-language commands where practical
- noisy environments where practical

Language detection should be good enough that ARIA does not require the user to manually select a language.

Do not train a speech model from scratch.

Evaluate existing lightweight local speech-recognition implementations.

The system should benchmark:

- model size
- startup time
- transcription latency
- CPU usage
- RAM usage
- command accuracy
- language/accent robustness

The first version should prioritize **short-command recognition** rather than long-form transcription.

---

# 9. Intent System

ARIA should define a fixed action schema.

Initial actions may include:

```text
OPEN_APPLICATION
CLOSE_APPLICATION
FOCUS_APPLICATION
MINIMIZE_WINDOW
MAXIMIZE_WINDOW
RESTORE_WINDOW
RESIZE_WINDOW
MOVE_WINDOW
OPEN_FOLDER
OPEN_FILE
CREATE_FOLDER
RENAME_FILE
MOVE_FILE
COPY_FILE
DELETE_FILE
TAKE_SCREENSHOT
START_SCREEN_RECORDING
STOP_SCREEN_RECORDING
OPEN_WEBSITE
SEARCH_WEB
SEARCH_YOUTUBE
PLAY_YOUTUBE
TYPE_TEXT
COPY
PASTE
SET_VOLUME
MUTE
UNMUTE
LOCK_COMPUTER
SHUTDOWN
```

This list should expand gradually.

Do not create hundreds of commands initially.

---

# 10. Structured Action Format

All execution should pass through structured actions.

Example:

```json
{
  "action": "OPEN_APPLICATION",
  "target": "camera"
}
```

Example:

```json
{
  "action": "RESIZE_WINDOW",
  "target": "camera",
  "width_ratio": 0.20,
  "height_ratio": 0.20,
  "position": "TOP_RIGHT"
}
```

Example:

```json
{
  "action": "MOVE_FILE",
  "source": "C:\\Users\\User\\Videos\\recording.mp4",
  "destination": "C:\\Users\\User\\Videos\\ARIA\\recording.mp4"
}
```

The schema must be validated before execution.

---

# 11. Window Management

Windows-first implementation should use native APIs wherever possible.

Investigate/use:

- pywin32
- Win32 APIs
- Windows UI Automation
- pywinauto where useful

Required capabilities:

```text
get active window
get window title
get window bounds
set window position
set window size
minimize
maximize
restore
focus
```

ARIA must support relative window operations.

Example:

> "Make it 10% smaller."

If the current window width is:

```text
1000 px
```

10% smaller means:

```text
900 px
```

The exact interpretation should be defined and consistent.

---

# 12. Stateful Command System

ARIA must maintain a small in-memory session state.

Example:

```python
session_state = {
    "active_target": ...,
    "last_action": ...,
    "last_window": ...,
    "last_rect": ...,
    "last_file": ...,
    "last_recording": ...,
    "conversation_context": ...
}
```

Example:

User:

> "Open Camera."

State:

```text
active_application = Camera
```

User:

> "Make it one-fifth of the screen."

ARIA resolves:

```text
"it" → Camera window
```

User:

> "Move it to the top right."

ARIA resolves:

```text
"it" → same Camera window
```

State should be explicit and deterministic.

Do not rely on an LLM for basic reference resolution.

---

# 13. Relative Commands

ARIA must support relative commands.

Examples:

```text
"make it 10% smaller"
"make it a little bigger"
"move it 100 pixels left"
"move it slightly down"
"make it louder"
"reduce the volume by 10%"
"make this window half the size"
```

The command interpreter should transform these into deterministic changes against known state.

---

# 14. Screen Recording

Use an existing local recording mechanism rather than implementing video capture from scratch.

Potentially use FFmpeg or appropriate Windows-native capture APIs.

The initial requirement:

```text
START_SCREEN_RECORDING
STOP_SCREEN_RECORDING
```

The system should track:

```text
recording_started_at
recording_file
recording_status
```

When the user says:

> "Save the recording to the Videos folder."

ARIA should know which recording is being referenced.

---

# 15. Filesystem Operations

ARIA should support common local file operations.

Initial capabilities:

```text
create
rename
move
copy
open
list
delete
```

Known folders should be resolved through OS APIs rather than hardcoded paths.

For Windows, resolve standard folders such as:

- Desktop
- Documents
- Downloads
- Videos
- Pictures

Do not assume:

```text
C:\Users\<username>\
```

manually when Windows provides an appropriate API.

---

# 16. Browser Automation

Browser automation should be implemented separately from desktop automation.

Preferred technology:

**Playwright**

Initial capabilities:

```text
open browser
navigate
search
click
type
submit
download
read page state
```

Example:

> "Open YouTube and play Blinding Lights."

Potential execution:

```text
OPEN_BROWSER
→ NAVIGATE_TO_YOUTUBE
→ SEARCH
→ SELECT_RESULT
→ PLAY
```

Avoid screenshot-based browser clicking when DOM/browser automation can accomplish the same action.

---

# 17. Risk and Permission System

The risk system must be deterministic.

Do NOT ask an LLM:

> "Is this dangerous?"

Instead, every supported action has a predefined risk category.

Example:

```text
OPEN_APPLICATION       → NONE
FOCUS_APPLICATION      → NONE
RESIZE_WINDOW          → NONE
MOVE_WINDOW            → NONE
OPEN_FOLDER            → NONE
TAKE_SCREENSHOT        → LOW
START_RECORDING        → LOW
SAVE_FILE              → LOW
MOVE_FILE              → MEDIUM
COPY_FILE              → LOW
DELETE_FILE            → HIGH
SEND_MESSAGE           → HIGH
SEND_EMAIL             → HIGH
PURCHASE               → HIGH
INSTALL_SOFTWARE       → HIGH
UNINSTALL_SOFTWARE     → HIGH
SYSTEM_SHUTDOWN        → HIGH
CHANGE_SECURITY        → HIGH
RUN_ARBITRARY_COMMAND  → HIGH
```

Exact categories can evolve.

The model must never be able to bypass the risk engine.

Flow:

```text
model output
     ↓
schema validation
     ↓
risk lookup
     ↓
permission decision
     ↓
executor
```

---

# 18. Confirmation UI

For medium/high-risk actions:

```text
┌────────────────────────────────────────┐
│              ARIA                      │
│                                        │
│ Confirmation required                  │
│                                        │
│ ARIA wants to delete:                  │
│ C:\Users\User\Downloads\file.pdf       │
│                                        │
│        [ Cancel ]   [ Confirm ]        │
└────────────────────────────────────────┘
```

The confirmation must clearly state:

- what action will happen
- what target is affected
- relevant consequences

Do not hide important information behind vague text such as:

> "Are you sure?"

---

# 19. Undo / Rollback

The action architecture should support reversibility.

Each executor should optionally return:

```text
result
undo_action
```

Example:

```text
MOVE_FILE
```

could return:

```text
undo = MOVE_FILE(destination → source)
```

For deletion, initially use the Recycle Bin rather than permanent deletion where practical.

Window operations should maintain a small history:

```text
previous rectangle
current rectangle
```

This allows future commands such as:

> "Undo that."

Undo is not required for the first MVP but the architecture should not make it impossible.

---

# 20. Privacy

ARIA should be designed around local processing.

Do not upload by default:

- microphone recordings
- screenshots
- screen recordings
- files
- file contents
- browser history
- passwords
- clipboard contents
- application data

If cloud AI is eventually supported, it must be:

1. Explicitly enabled.
2. Clearly visible.
3. Separate from the local core.
4. Documented regarding what data leaves the device.

---

# 21. Content Handling

ARIA is not intended to be a content moderation system.

The presence of:

- NSFW files
- private images
- private videos
- sensitive documents
- personal browser history

on the user's machine should not automatically cause ARIA to refuse ordinary computer operations.

Safety is based primarily on the **requested action**, not the classification of personal content.

---

# 22. Latency Engineering

Latency is a first-class project metric.

Do not simply say:

> "ARIA is fast."

Measure it.

Track at least:

```text
T0 = user input begins
T1 = speech recognition starts
T2 = speech recognition completes
T3 = intent recognized
T4 = action generated
T5 = risk check completes
T6 = execution starts
T7 = execution completes
```

Calculate:

```text
ASR latency
intent latency
routing latency
risk-check latency
execution latency
end-to-end latency
```

For text commands, measure separately from voice commands.

---

# 23. Target Latency

Do not make the unrealistic promise that every voice interaction will complete in 30–50 ms.

Speech recognition itself introduces latency.

Instead, target:

### UI activation

Hotkey/wake-word → listening UI:

**<50 ms target**

### Deterministic routing

Recognized command → action:

**single-digit to tens of milliseconds target**

### Native actions

Command → OS action:

**as close to instantaneous as practical**

### Voice interaction

Speech completion → action:

Optimize aggressively, but benchmark honestly.

The project should report measured latency rather than making arbitrary claims.

---

# 24. Resource Efficiency

ARIA should eventually be tested on multiple classes of hardware.

Measure:

```text
RAM at idle
RAM during ASR
RAM during local model inference
CPU at idle
CPU during ASR
CPU during execution
GPU usage
startup time
disk footprint
```

The goal is to determine whether ARIA can comfortably operate on:

### Tier A
Modern high-end laptop

### Tier B
Typical 16 GB RAM laptop

### Tier C
Older 8 GB RAM laptop

The project should not assume a dedicated GPU.

The core fast path should work on CPU.

---

# 25. Language Support

The system should not initially attempt to support every language.

First benchmark:

- English
- Indian English
- Hindi
- Hinglish / mixed English-Hindi

Then expand based on testing.

Language identification should preferably be performed locally.

The architecture should allow:

```text
audio
→ language detection
→ appropriate ASR configuration/model
→ command interpretation
```

However, language detection must not introduce unnecessary latency for obvious commands.

Potential optimization:

If the user has a configured preferred language, use it as the default and only perform broader language detection when confidence is low.

---

# 26. Reliability

A successful command means more than correctly understanding the sentence.

ARIA must verify execution where practical.

Example:

User:

> "Open Camera."

Bad:

```text
command parsed successfully
```

Good:

```text
Camera process/window detected
→ action succeeded
```

For browser operations, verify expected page state.

For file operations, verify the destination exists.

For window operations, verify the resulting rectangle.

Track:

```text
intent_accuracy
execution_success_rate
verification_success_rate
```

---

# 27. Error Recovery

ARIA should handle:

- application not installed
- application failed to launch
- window not found
- browser failed to load
- file not found
- permission denied
- recording failed
- action timed out
- ambiguous command
- low speech confidence

Example:

> "Open Photoshop."

If Photoshop is not installed:

> "I couldn't find Photoshop on this computer."

Do not silently fail.

---

# 28. Project Phases

## PHASE 0 — Repository + Architecture

Goal:

Create the project foundation.

Tasks:

- Create GitHub repository named `ARIA`.
- Create `context.md`.
- Create initial README.
- Define architecture.
- Define action schema.
- Define risk schema.
- Create Python environment.
- Establish logging.
- Establish configuration system.
- Establish test structure.

Deliverable:

```text
ARIA/
├── README.md
├── context.md
├── pyproject.toml
├── src/
├── tests/
└── docs/
```

Do not build AI yet.

---

# PHASE 1 — Deterministic Desktop Core

Goal:

Make ARIA useful without any AI.

Implement:

- application launcher
- window detection
- window movement
- window resizing
- minimize/maximize/restore
- focus
- filesystem operations
- screenshots
- volume controls

Commands can initially be text commands.

Example:

```text
open camera
resize camera 20%
move camera top right
```

Acceptance criterion:

The same command should produce the same result reliably.

---

# PHASE 2 — Stateful Commands

Goal:

Introduce context.

Implement:

- active application
- active window
- last action
- last target
- last file
- last recording
- previous window geometry

Test:

```text
open camera
make it 20% of the screen
move it top right
make it 10% smaller
move it slightly left
```

ARIA must resolve all references correctly.

---

# PHASE 3 — Voice Input

Goal:

Control the existing deterministic system with speech.

Implement:

- microphone capture
- local ASR
- command transcription
- speech confidence
- basic language detection
- command normalization

Do not add an LLM yet.

Test:

```text
open camera
open chrome
make it smaller
move it to the top right
start recording
stop recording
```

Acceptance criterion:

Voice commands should reliably map onto the existing deterministic command engine.

---

# PHASE 4 — Global Activation

Goal:

Make ARIA feel like a real assistant.

Implement:

- global hotkey
- minimal overlay
- listening indicator
- command execution indicator
- error indicator

Later:

- local wake word
- "Hey ARIA"

Do not sacrifice latency for visual polish.

---

# PHASE 5 — Risk Engine

Goal:

Add safe autonomy.

Implement:

- action risk metadata
- deterministic risk lookup
- confirmation dialog
- cancellation
- logging
- confirmation timeout

Test:

```text
open camera
→ immediate

resize window
→ immediate

delete file
→ confirmation

send message
→ confirmation

shutdown computer
→ confirmation
```

---

# PHASE 6 — Browser Automation

Goal:

Expand ARIA beyond Windows-native commands.

Implement Playwright-based capabilities:

- open browser
- navigate
- search
- type
- click
- YouTube search
- YouTube playback
- downloads
- basic web interaction

Example:

> "Open YouTube and play Blinding Lights."

No general-purpose LLM should be required for this workflow.

---

# PHASE 7 — Lightweight Local Intent Model

Goal:

Handle natural language without introducing significant latency.

Introduce a small local model only where rules are insufficient.

Input:

> "Could you make this window about a fifth of the screen and put it in the upper right?"

Output:

```json
{
  "action": "RESIZE_WINDOW",
  "target": "active_window",
  "width_ratio": 0.20,
  "position": "TOP_RIGHT"
}
```

The model must output only the defined action schema.

Implement:

- schema validation
- model timeout
- fallback to deterministic parser
- confidence handling
- latency measurement

---

# PHASE 8 — Complexity Router

Goal:

Automatically choose the cheapest execution path.

Example:

```text
"open notepad"
→ FAST PATH

"make this window slightly smaller"
→ SMART PATH

"open YouTube and search for..."
→ FAST/SMART PATH

"research this topic, create a document and save it"
→ AGENT PATH
```

This is one of ARIA's core architectural features.

---

# PHASE 9 — Local Agent

Goal:

Handle complex multi-step tasks.

Build:

- local planner
- browser interaction
- UI observation
- state tracking
- task decomposition
- execution
- recovery
- verification

Example:

> "Open Gemini, ask it why tigers are endangered, create a document, download it and save it in my Documents folder."

The agent should produce a plan, execute it, verify each important step, and report completion.

This path can be slower than simple commands.

---

# PHASE 10 — Vision / UI Fallback

Only after deterministic APIs and browser automation are mature.

Add:

- UI tree inspection
- screenshot understanding
- lightweight vision model
- visual element targeting

Fallback hierarchy:

```text
Native API
    ↓
UI Automation
    ↓
Browser DOM
    ↓
Accessibility tree
    ↓
Vision
    ↓
General agent reasoning
```

Never use vision if a faster deterministic interface exists.

---

# PHASE 11 — Performance Benchmarking

Create a reproducible benchmark suite.

Measure:

### Latency

- hotkey → popup
- speech → transcription
- transcription → intent
- intent → action
- action execution
- complete voice → action latency

### Accuracy

- command recognition
- intent accuracy
- execution success
- verification success

### Hardware

- CPU
- RAM
- GPU
- disk usage
- startup time

### Robustness

Test across:

- high-end laptop
- mid-range laptop
- older laptop
- different microphones
- different accents
- noisy environments

---

# PHASE 12 — Optimization

Only optimize after measurement.

Possible optimizations:

- model quantization
- model warm-up
- persistent ASR process
- model loading once at startup
- command caching
- preloaded application metadata
- rule-first routing
- avoiding unnecessary language detection
- parallelizing independent operations
- reducing UI overhead
- lazy-loading agent components
- keeping heavy models completely unloaded unless required

ARIA should ideally remain lightweight at idle.

---

# 29. Initial Repository Structure

Recommended:

```text
ARIA/
│
├── README.md
├── context.md
├── LICENSE
├── pyproject.toml
├── .gitignore
│
├── src/
│   └── aria/
│       ├── __init__.py
│       ├── main.py
│       │
│       ├── core/
│       │   ├── router.py
│       │   ├── intent.py
│       │   ├── actions.py
│       │   ├── schema.py
│       │   ├── state.py
│       │   └── executor.py
│       │
│       ├── voice/
│       │   ├── microphone.py
│       │   ├── asr.py
│       │   ├── language.py
│       │   └── wakeword.py
│       │
│       ├── desktop/
│       │   ├── applications.py
│       │   ├── windows.py
│       │   ├── filesystem.py
│       │   ├── recording.py
│       │   └── system.py
│       │
│       ├── browser/
│       │   ├── browser.py
│       │   ├── navigation.py
│       │   ├── youtube.py
│       │   └── downloads.py
│       │
│       ├── ai/
│       │   ├── local_model.py
│       │   ├── parser.py
│       │   └── planner.py
│       │
│       ├── safety/
│       │   ├── risk.py
│       │   ├── permissions.py
│       │   └── confirmation.py
│       │
│       ├── agent/
│       │   ├── observer.py
│       │   ├── planner.py
│       │   ├── executor.py
│       │   └── recovery.py
│       │
│       └── ui/
│           ├── overlay.py
│           └── tray.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── latency/
│   └── benchmark/
│
├── docs/
│   ├── architecture.md
│   ├── commands.md
│   ├── security.md
│   └── benchmarks.md
│
└── scripts/
    ├── benchmark.py
    └── setup.py
```

This structure can change as implementation reveals better boundaries. Do not over-engineer empty modules.

---

# 30. Development Rules for Codex

When implementing ARIA:

1. **Do not build the entire project at once.**
2. Complete one phase before introducing the next major dependency.
3. Keep the fast path independent from the local LLM.
4. Do not add a heavyweight model merely because it makes parsing easier.
5. Prefer native OS APIs over screenshot-based computer control.
6. Prefer DOM/browser APIs over browser vision.
7. Keep action execution deterministic.
8. Validate all model-generated actions against a fixed schema.
9. The model must never bypass the risk engine.
10. Keep all core processing local.
11. Measure latency before optimizing.
12. Do not claim latency numbers without benchmarking them.
13. Keep dependencies minimal.
14. Do not add cloud APIs to the core architecture.
15. Keep platform-specific code isolated so other OS implementations can be added later.
16. Write tests for every executor.
17. Log failures and execution times.
18. Prefer reversible operations where possible.
19. Do not implement complex agent functionality before the deterministic core is reliable.
20. Every new feature should answer: **Can this be done without an LLM?** If yes, prefer that implementation.

---

# 31. Initial MVP Definition

The first meaningful MVP is NOT a general AI agent.

MVP:

```text
User
 ↓
Global hotkey
 ↓
Local speech recognition
 ↓
Command parser
 ↓
Deterministic action
 ↓
Windows
```

It must successfully support:

```text
open camera
open chrome
open notepad
resize window
move window
minimize
maximize
restore
create folder
open folder
take screenshot
start recording
stop recording
save/move recording
volume controls
```

And stateful commands:

```text
open camera
make it one fifth of the screen
move it to the top right
make it 10% smaller
```

And permission handling:

```text
delete file
→ confirmation

shutdown
→ confirmation
```

If this works reliably and quickly, ARIA already has a useful core.

---

# 32. Long-Term Vision

Eventually ARIA should feel like a local operating-system-level assistant.

A user should be able to say:

> "ARIA, open Chrome."

> "Move it to the right."

> "Make it smaller."

> "Open YouTube."

> "Play some Daft Punk."

> "Actually pause that."

> "Start recording."

> "Open my Downloads."

> "Move today's recordings into a folder called Project Demo."

> "Open Gemini."

> "Ask it to research this topic."

> "Download the resulting document."

> "Save it with today's date."

ARIA should maintain enough short-term context to understand these references naturally.

Simple actions should remain almost instantaneous.

Complex actions should automatically switch to a more capable local agent.

The user should not have to know which mode is being used.

---

# 33. Core Technical Thesis

The central thesis of ARIA is:

> **A computer assistant does not need maximum intelligence for every action. It needs adaptive intelligence.**

For a deterministic task:

```text
No LLM.
```

For a structured natural-language task:

```text
Tiny local model.
```

For a complex task:

```text
Local agent.
```

The system should dynamically choose the appropriate level of intelligence based on task complexity.

This should minimize:

- latency
- CPU usage
- RAM usage
- unnecessary inference
- network dependency
- privacy exposure

while maintaining high execution reliability.

---

# 34. Success Criteria

ARIA should eventually demonstrate:

### Responsiveness
Simple commands feel nearly instantaneous.

### Accuracy
Common commands are executed correctly.

### Locality
Core functionality works without cloud APIs.

### Resource efficiency
The assistant can run comfortably on ordinary laptops.

### Stateful interaction
Follow-up commands correctly reference previous actions.

### Safety
High-impact actions require confirmation.

### Reliability
Actions are verified and failures are clearly reported.

### Extensibility
New actions can be added without rewriting the architecture.

### Intelligence scaling
ARIA can transition from deterministic automation to local AI reasoning only when necessary.

---

# 35. First Task

Do NOT start by implementing voice recognition, LLMs, browser agents, vision, or wake words.

Start with:

```text
PHASE 0
↓
PHASE 1
```

The first working demonstration should be:

```text
ARIA running
        ↓
text command:
"open camera"
        ↓
Camera opens
```

Then:

```text
"make it one fifth of the screen"
        ↓
Camera resizes
```

Then:

```text
"move it to the top right"
        ↓
Camera moves
```

Then:

```text
"make it 10% smaller"
        ↓
Camera resizes relative to its current state
```

Then add voice.

The objective is to establish the **deterministic execution core first**.

Everything else should be layered on top of this foundation.

---

# 36. Guiding Principle

Do not try to make ARIA intelligent everywhere.

Make it:

**fast where it can be fast,**

**intelligent where it needs intelligence,**

**local wherever possible,**

**stateful when context matters,**

**and cautious only when an action has meaningful consequences.**

That is the product.

---

# 37. Core Architectural Principle — Capability-Driven Design

> **ARIA must be capability-driven rather than application-driven. Application names, files, windows, websites, and other targets should be discovered dynamically whenever possible. The code should define what ARIA can do, not enumerate every thing it can do it to.**

This is a core architectural principle of the project and must guide implementation decisions across all phases.

