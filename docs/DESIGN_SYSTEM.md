# EchoTrace — Design System

## 1. Direction: the analyst's light table

EchoTrace is used by someone reading hundreds of public comments to decide which ones are one voice. The interface should feel like a clean examination desk: comments are **documents** laid on a cool, neutral surface, and the relationships between them are drawn as **threads**. One element carries all the boldness, the **evidence board**; everything around it is quiet and orderly.

Avoided on purpose: dashboard card grids, dark "hacker" themes, newspaper pastiche, and red-string conspiracy boards. The subject is civic process, so the tone is calm, exact, and fair.

## 2. Tokens (`frontend/src/styles/tokens.css`)

### Colour
| Token | Light | Dark | Use |
|---|---|---|---|
| `--desk` | `#E4E9EC` | `#1C2329` | App background, board surface |
| `--paper` | `#FFFFFF` | `#262F37` | Comment sheets, panels |
| `--ink` | `#18212C` | `#E8EDF1` | Primary text |
| `--ink-soft` | `#566271` | `#A5B1BD` | Secondary text, metadata |
| `--rule` | `#C8D0D7` | `#3A4550` | Borders, dividers |
| `--thread` | `#2C5A87` | `#7FAEDB` | Similarity threads, links, focus |
| `--marker` | `#F6DC5A` | `#8A7A1E` | Highlighter behind shared phrasing |
| `--campaign` | `#9C2A4A` | `#E08AA2` | `coordinated_paraphrase_campaign` |
| `--form` | `#5B4B9A` | `#B3A6E6` | `form_letter` |
| `--organic` | `#2E7556` | `#7FC7A5` | `organic_agreement` |
| `--unsure` | `#6B7580` | `#9AA4AE` | `insufficient_evidence` |

Colour never carries meaning alone: every verdict colour appears with its text label, and thread style (below) encodes the reword/copy distinction with dash pattern too.

### Type
- **Public Sans** (Google Fonts) for all interface text. It is the typeface of the U.S. Web Design System, which grounds the product in its civic subject. Use tabular figures (`font-variant-numeric: tabular-nums`) for every metric.
- **Source Serif 4** for comment text only. Anything in serif is a real submitted document; anything in sans is EchoTrace talking. This separation is the core typographic rule.
- Scale (rem): 0.8125 · 0.875 · 1 · 1.125 · 1.375 · 1.75. Body 1rem / 1.5 (sans), 1.0625rem / 1.65 (serif). Weights: 400, 600 only.
- Sentence case everywhere. No all-caps labels. Line length ≤ 72ch for comment text.

### Space, shape, depth
- 4px base: 4, 8, 12, 16, 24, 32, 48.
- Radius: sheets 2px (paper), controls 6px, chips 999px. Different radii encode different object kinds.
- Depth: only comment sheets on the board have a shadow (`0 1px 2px rgb(24 33 44 / .12), 0 4px 12px rgb(24 33 44 / .06)`), because they are the physical objects on the desk. Panels are flat with a `--rule` border.

## 3. Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ EchoTrace   Dockets   Check a comment                  provider status│
├───────────────┬──────────────────────────────────────┬───────────────┤
│ Families       │            EVIDENCE BOARD            │ Verdict drawer │
│ (ranked list)  │                                      │                │
│ ▸ 212 · 0.81   │     ○      ○                          │ Type + conf.   │
│   campaign     │   ○   ┌──────────┐   ○                │ Rationale w/   │
│ ▸ 48 · 0.64    │ ○ ----│  medoid  │---- ○              │ citation chips │
│   form letter  │   ○   └──────────┘   ○                │ Metrics table  │
│ ▸ 9 · 0.30     │     ○      ○                          │ Review bar     │
│   organic      │                                      │ Agent trace ▾  │
├───────────────┴──────────────────────────────────────┴───────────────┤
│ Compare tray (opens on member click): Sheet A  |  Sheet B, shared phrasing highlighted │
└──────────────────────────────────────────────────────────────────────┘
```
- Desktop ≥1200px: three columns (280px / fluid / 360px). 768–1199px: list collapses into a top selector; drawer becomes a bottom sheet. <768px: board replaced by a member list sorted by similarity (graphs are unusable at phone width).
- Text is left-aligned throughout; numbers right-aligned in tables.

## 4. The evidence board (signature element)

Built with `@xyflow/react`. Encoding:
| Visual | Meaning |
|---|---|
| Centre sheet, larger, `--ink` 2px border | Medoid (most representative comment) |
| Surrounding sheets (excerpt, 3 lines, serif) | Members; radius from centre = `1 − sim` |
| Thread thickness 1–4px | Meaning similarity to medoid |
| **Dashed** thread | Low word overlap (lex < 0.35): same meaning, different words |
| **Solid** thread | High word overlap: copied text |
| Small dot on sheet corner, `--thread` fill scaled by value | AI-style signal |
| Cited sheets | 2px `--campaign`/verdict-colour outline + citation number |

The dashed/solid distinction is the product's idea made visible: a board full of dashed threads *is* a reworded campaign.

Interactions: click a sheet → select it and open the compare tray against the medoid; shift-click two sheets → compare them. Citation chips in the drawer select and centre their sheet. Pan/zoom enabled; "Reset view" button. Max 60 nodes; more shows "Showing 60 of 212 — view all in list."

Motion: one orchestrated moment only. When an analysis finishes, members settle from the centre outward along their threads (400ms, ease-out). Respect `prefers-reduced-motion` (no animation).

## 5. Components

| Component | Purpose | Notes |
|---|---|---|
| `AppShell` | Header, nav, provider status | Status shows "Configured"/"Missing key" per provider |
| `DocketForm` | Add docket ID | Validate pattern `^[A-Z0-9-]+$`; button "Fetch comments" |
| `SampleList` | Load bundled real dockets | Button "Load sample" |
| `IngestProgress` | Fetched / total, skipped | Linear bar + counts; resumable message on partial |
| `PipelineStepper` | Seven steps with status | Real sequence, so numbering is appropriate here |
| `FamilyList` | Ranked families | Row: size, score, `VerdictTag`, review status |
| `VerdictTag` | Type label | Colour dot + text; never colour alone |
| `EvidenceBoard` | §4 | |
| `CommentSheet` | One comment on the board or in lists | Serif body, submitter label, posted time |
| `VerdictDrawer` | Verdict, confidence, rationale, metrics, review | |
| `CitationChip` | Numbered link to a cited comment | Keyboard focusable |
| `MetricTable` | §4.5 metrics with one-line explanations | Hover/focus reveals the formula |
| `CompareTray` | Side-by-side sheets | Shared phrases on `--marker` highlight |
| `ReviewBar` | Confirm / Reject / Unsure + note | Buttons: "Confirm campaign", "Reject", "Mark unsure"; toast repeats the verb |
| `AgentTrace` | Collapsible step list | Thought, tool, short observation |
| `EmptyState`, `ErrorState` | Direction on what to do next | See copy rules |

## 6. Copy rules

Vocabulary (use consistently): **family** (a group of similar comments), **campaign** (a coordinated family), **representative comment** (medoid), **reworded** (same meaning, different words), **AI-style signal (unverified)**.

Never use: fake, bot, fraud, sockpuppet, astroturf, "AI detected". The product cannot verify identities and must not imply it.

Verdict phrasing:
- Campaign: "Likely one coordinated campaign — 212 reworded comments, 81% within 24 hours."
- Form letter: "Form letter — 48 near-identical comments."
- Organic: "Similar views, independently worded."
- Insufficient: "Not enough evidence to call this a campaign."

Empty and error states tell the user the next action: "No dockets yet. Add a docket ID or load a sample." · "Gemini key missing. Add GEMINI_API_KEY to backend/.env and restart." · "Rate limit reached at comment 340 of 500. Fetching resumes automatically."

Privacy: submitter names show as given by Regulations.gov (public record) but a header toggle "Hide names" replaces them with `Submitter a3f9` (hash prefix); default on for demos.

## 7. Accessibility floor

WCAG AA contrast for all text (tokens above pass on their paired backgrounds); visible focus ring `2px solid var(--thread)` offset 2px; every board action also reachable from the family member list; graph has an accessible table alternative ("View as list"); live region announces pipeline step changes; hit targets ≥ 40px.
