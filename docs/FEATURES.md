# Feature Inventory

Last updated: 2026-05-28

## Feature Status Legend

- Planned: accepted as part of the roadmap.
- Candidate: likely useful, but not committed yet.
- Future: intentionally deferred.
- Out of scope: not planned for the current project direction.

## Desktop Pet

| Feature | Status | Target |
| --- | --- | --- |
| Transparent pet window | Planned | M1 |
| Borderless window | Planned | M1 |
| Always-on-top behavior | Planned | M1 |
| Drag to move pet | Planned | M1 |
| Placeholder pet image | Planned | M1 |
| Rina image replacement folder | Planned | M1 |
| Tray menu | Planned | M2 |
| Right-click menu | Candidate | M2 |
| Pet state controller | Implemented | M2 |
| Idle state | Implemented | M2 |
| Follow state | Implemented | M2 |
| Talk state | Implemented | M2 |
| Sleep state | Implemented | M2 |
| Frame animation | Candidate | M5 |
| Live2D-style rendering | Future | M5 or later |

## LLM Chat

| Feature | Status | Target |
| --- | --- | --- |
| Compact chat input | Implemented | M3 |
| Chat bubble or panel | Implemented | M3 |
| Separate dialogue workspace window | Implemented | M2 |
| Bubble opens dialogue workspace | Implemented | M2 |
| Default chat-only dialogue layout | Implemented | M2 |
| Hidden or separate settings surface | Candidate | M3 |
| Rina Board dialogue theme hook | Candidate | M5 |
| OpenAI-compatible API adapter | Implemented | M3 |
| Configurable base URL | Implemented | M3 |
| Configurable model name | Implemented | M3 |
| Configurable API key | Implemented | M3 |
| Streaming output | Implemented | M3 |
| Basic conversation history | Implemented | M3 |
| System prompt support | Implemented | M3 |
| Provider abstraction | Started | M3 |
| Image payload shape for future screenshot handoff | Started | M3-M4 |
| Long-context summarization | Planned | R1 |
| Token or length budgeting | Planned | R1 |
| Provider/model capability hints | Planned | R1 |
| Multi-provider UI | Candidate | Later |
| Local model support | Candidate | Later |

## Desktop Interaction

| Feature | Status | Target |
| --- | --- | --- |
| Global shortcut for selection | Out of scope | Not planned |
| Visible capture entry point | Implemented | M4 |
| Windows system screen clipping | Implemented | M4 |
| Custom screen overlay | Deferred | Later, only if safe |
| Region rectangle selection | Implemented | M4 via OS clipper |
| Screenshot capture | Implemented | M4 via clipboard |
| Clipboard image paste | Implemented | M4 |
| Send selected image to model | Implemented | M4 |
| Vision model fallback handling | Started | M4-M6 |
| OCR extraction | Candidate | Later |
| Drag file onto pet | Candidate | Later |

## Quick Actions

| Feature | Status | Target |
| --- | --- | --- |
| Explain selected region | Candidate | Prompt template |
| Ask about selected region | Candidate | Prompt template |
| Extract text from region | Candidate | Later |
| Translate selected region | Candidate | Later |
| Summarize selected region | Candidate | Prompt template |
| Generate study notes | Candidate | Later |

The study-note workflow is treated as an application of screenshot and LLM features, not as an independent early milestone.

Quick-action entries are currently lightweight prompt templates, not a required automation framework. They can be hidden or removed if the dialogue toolbox feels too busy.

## Character and Prompting

| Feature | Status | Target |
| --- | --- | --- |
| Placeholder prompt | Implemented | M3 |
| Rina character prompt | Started | M3-M5 |
| State-specific pet images | Planned | A1 |
| Emotion style guide | Future | M5 |
| Prompt files in `prompts` | Planned | M3-M5 |
| Code-level pet profile replacement | Implemented | M2 |
| Character switching UI | Candidate | M5 or later |
| Project-specific Codex skill | Candidate | M5 or later |
| Rina pet skill | Candidate | M5 or later |

## Settings and Reliability

| Feature | Status | Target |
| --- | --- | --- |
| API settings persistence | Candidate | S1 |
| Pet position persistence | Candidate | M2 or later |
| Logs | Planned | R1-M6 |
| Error reporting UI | Planned | R1-M6 |
| Stop/cancel real-stream QA | Planned | R1 |
| Vision support fallback polish | Planned | R1-M4P |
| Windows packaging | Future | M6 |
| Start on boot | Future | M6 |
| Auto-update | Future | Later |

## Asset Locations

Current planned Rina asset folder:

```text
E:\OurDeskPet\assets\rina
```

Current known source folder:

```text
E:\API_test\RinaChanBoard\img
```

When the app is implemented, the first pet image should be read from a stable app asset path rather than directly depending on `E:\API_test`.
