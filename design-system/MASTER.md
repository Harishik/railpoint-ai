# RailPoint-AI — Design System (Master)

Source of truth for all UI. Page-specific deviations live in `design-system/pages/<page>.md`
and override this file; if no page file exists, these rules apply exclusively.

---

## 1. What this product is, and what it must not look like

A **railway signalling operations console**. The reference points are interlocking
panels, train-describer displays and ISA-101 control-room HMI — not SaaS dashboards.

**The failure mode to avoid** is the generic AI-generated dashboard: purple-to-blue
gradients, evenly-rounded cards floating on a light grey field, an emoji or a Lucide
icon in a pastel circle above every stat, decorative motion, and colour used because
it looks nice. In a safety domain that aesthetic is not merely bland, it is **wrong**:
colour here carries state, and spending it on decoration destroys the one channel an
operator relies on.

Three commitments follow from that:

1. **Colour is state.** Every hue in the interface maps to a machine condition. There
   are no decorative colours. Brand expression comes from typography, density and
   motion instead.
2. **Density over whitespace.** Control rooms are information-dense by necessity. We
   use spacing for grouping, not for luxury.
3. **The waveform is the hero.** The most interactive surface is the signal itself.
   Interaction budget goes there, not into page transitions.

---

## 2. Colour — derived from the machine, not from a palette generator

The point machine's own indication circuit is a three-state signal (see `docs/DATA.md`):
**+23 V locked Normal · ~0 V in transit · −23 V locked Reverse**. The interface adopts
those three states as its primary colour semantics, so the palette *is* the domain model.

```
--state-normal      oklch(0.72 0.15 155)   locked at Normal (정위)
--state-reverse     oklch(0.78 0.14  75)   locked at Reverse (반위)
--state-transit     oklch(0.72 0.12 230)   in transit, no position detected
--state-fault       oklch(0.63 0.20  25)   blocked / failed throw
--state-degraded    oklch(0.75 0.16  55)   degrading, still operable
--state-unknown     oklch(0.55 0.02 250)   no telemetry
```

Control-room dark is the **primary** theme (operators work in dim rooms); light is a
first-class alternative, not an afterthought. Surfaces are a cool near-black with a
slight blue cast — a pure `#000` field makes the signal colours glare.

```
--bg          oklch(0.16 0.012 250)    --surface-1   oklch(0.20 0.014 250)
--surface-2   oklch(0.24 0.016 250)    --surface-3   oklch(0.28 0.018 250)
--border      oklch(0.34 0.018 250)    --border-strong oklch(0.44 0.02 250)
--text        oklch(0.96 0.005 250)    --text-muted  oklch(0.72 0.012 250)
```

**Rules.** Every state must carry a **shape or label as well as a hue** — a colour-blind
operator must never lose information (`color-not-only`, `color-not-decorative-only`).
Contrast is verified independently per theme: body ≥ 4.5:1, large/UI glyphs ≥ 3:1,
data marks vs background ≥ 3:1. Dark mode uses desaturated tonal variants, never
inverted light values.

---

## 3. Typography — chosen for a reason

**IBM Plex Sans** (UI) + **IBM Plex Sans KR** (Korean) + **IBM Plex Mono** (all data).

This is not a default. Three reasons it is the right face here:

- The interface is **bilingual KO/EN** by requirement, and Plex is one of very few
  families with a purpose-designed Korean companion that shares metrics and voice.
  Pairing a Latin face with an unrelated Korean fallback is exactly the seam that makes
  bilingual UI look unconsidered.
- Plex was drawn as an **engineering and industrial** typeface. It carries the right
  register for signalling equipment without costume-drama technical styling.
- Plex Mono gives **tabular figures**, mandatory for currents, voltages, RUL counts and
  timers that must not reflow as digits change (`number-tabular`).

```
--font-ui    "IBM Plex Sans", "IBM Plex Sans KR", system-ui, sans-serif
--font-mono  "IBM Plex Mono", ui-monospace, monospace
```

**Every numeric value renders in `--font-mono` with `font-variant-numeric: tabular-nums`.**
Scale: 12 · 13 · 14 · 16 · 20 · 24 · 32. Body 14–16px, line-height 1.5. Weights carry
hierarchy: 600 headings, 500 labels, 400 body. 12px is permitted **only** for dense table
metadata, never for prose.

---

## 4. Motion — meaning only, and interruptible

Micro-interactions 150–200ms; view transitions ≤ 300ms; **exits at ~65% of enter**.
`ease-out` entering, `ease-in` leaving, spring only for direct-manipulation drag.

Motion must express cause and effect (`motion-meaning`). Three places earn it:

- **Waveform reveal** — the trace draws along its own sample index, so the animation
  *is* the throw replaying. Duration proportional to capture length, capped at 600ms.
- **Indication state change** — a machine node transitions through the real three-state
  sequence rather than cutting between colours. The animation shows the physics.
- **Alarm arrival** — one attention pulse, then settle. **Never loop.** A pulsing alarm
  in a control room becomes wallpaper within a minute and stops being seen.

Everything else is still. No entrance animation on page load, no staggered card reveals,
no parallax. `prefers-reduced-motion` disables all of the above and jumps to end state —
non-negotiable in a safety context. Animate `transform`/`opacity` only; no animation may
cause reflow.

---

## 5. Layout

Schematic-first. The primary surface is an **SVG interlocking diagram** — point machines
as nodes on a track layout, coloured by state — because that is how signalling staff
already read their territory. It is navigation and status in one object; clicking a node
opens that machine. A sortable fleet table sits beneath it for the cases where you know
the machine ID.

Spacing on a strict 4px rhythm: `4 8 12 16 24 32 48`. Breakpoints `768 / 1024 / 1440`;
sidebar navigation at ≥1024, collapsing to a top bar below (`adaptive-navigation`).
Fixed header reserves its own offset so content never hides behind it. Wide tables and
the schematic scroll inside their own `overflow-x: auto` container — **the page body
never scrolls horizontally.**

Z-index scale: `0 / 10 dropdown / 20 sticky / 40 overlay / 100 modal / 1000 toast`.

---

## 6. Charts and signals

Charts follow `dataviz` discipline plus the domain rules above:

- Grid lines low-contrast; data marks never competing with decoration.
- Axes labelled with **units** (A, V, cycles, samples). Time granularity always explicit.
- Legends interactive — clicking a series toggles it (`legend-interactive`).
- Tooltips reachable by keyboard, not hover-only (`tooltip-keyboard`).
- The healthy reference band renders *behind* the live trace so deviation reads instantly.
- Phase boundaries (unlock · throw · lock · indication) marked on the axis, because the
  whole feature model is phase-aware and the operator should see the same decomposition
  the model uses.
- Every chart has an accessible text summary of its key insight (`screen-reader-summary`)
  and a data-table alternative.
- Empty, loading and error states are designed, not left blank: skeletons for >300ms,
  an explicit retry on failure.

---

## 7. Interaction budget — where "highly interactive" is spent

Ranked. Effort goes to the top of this list:

1. **Waveform inspection** — brush to zoom, scrub for per-sample readout, overlay any
   two events, toggle channels, pin a healthy reference.
2. **Schematic** — hover previews state and last event; click drills in; keyboard
   traversable node-to-node.
3. **Explanation** — SHAP contributions expand from the feature that produced them and
   highlight the corresponding span on the waveform. Clicking evidence moves the chart.
4. **Alert triage** — acknowledge / assign / resolve inline with **undo** (`undo-support`).
5. **Copilot** — streams its answer, cites the retrieved maintenance code, links back to
   the event.

Everything not on this list is static by default.

---

## 8. Non-negotiables before any UI ships

- Contrast verified **independently** in dark and light; not inferred from one theme.
- Full keyboard path: tab order matches visual order, visible 2px focus ring, no traps.
  Focus rings are never removed.
- Icons are SVG from **one** family at consistent stroke width. **No emoji as icons.**
- Every icon-only control has an `aria-label`; every state has a text or shape cue.
- All numerals tabular; no layout shift as values update.
- `prefers-reduced-motion` honoured everywhere.
- Loading >300ms shows a skeleton that reserves final dimensions (CLS < 0.1).
- Tested at 1440 / 1024 / 768, and with the OS at largest text size.

---

## Appendix — measured contrast

Verified in the running app by rasterising each token through a canvas and
computing WCAG relative luminance (parsing the `oklch()` strings directly, as a
first attempt did, silently produces nonsense). Both themes measured
independently, never inferred from one another.

| Token vs `surface-1` | Dark | Light | Floor |
|---|---|---|---|
| `ink` | 16.07 | 17.35 | 4.5 |
| `ink-dim` | 7.86 | 7.79 | 4.5 |
| `ink-faint` | **5.24** | **5.48** | 4.5 |
| `normal` | 8.33 | — | 3.0 |
| `reverse` | 9.46 | — | 3.0 |
| `fault` | 5.28 | — | 3.0 |

`ink-faint` originally measured **4.22 and failed**. It carries labels and
metadata throughout the interface, so the token was lightened rather than the
requirement waived.
