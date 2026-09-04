# Design system

This UI is not styled freehand. It is derived from a Claude Design project, and every visual
decision below comes from that project or from the design system it imports. **Read this before
changing anything under `frontend/src/styles/` or `frontend/src/components/`.**

## Provenance

| | |
|---|---|
| Design project | **Timetable Generator** — `9e49658b-89f5-4a63-a670-3af294cd3e88` |
| Canvas file | `Timetable Generator.dc.html` |
| Design system | **Apple Design System** — `apple-design-system-af240dc4-b8f2-427f-a69a-681d42f9b7b5` |
| URL | <https://claude.ai/design/p/9e49658b-89f5-4a63-a670-3af294cd3e88> |

Re-read it with the `DesignSync` tool (authorize once with `/design-login`):

```
DesignSync list_files  projectId=9e49658b-89f5-4a63-a670-3af294cd3e88
DesignSync get_file    projectId=…  path="Timetable Generator.dc.html"
DesignSync get_file    projectId=…  path="_ds/apple-design-system-…/readme.md"
```

`frontend/src/styles/ds/` is a **verbatim copy** of the project's `_ds/…/styles.css` and
`_ds/…/tokens/*.css` (verified byte-identical). Never hand-edit those files — re-pull them. Anything
app-specific belongs in `frontend/src/styles/app.css`.

`support.js` in the design project is the canvas runtime (`x-dc`, `sc-if`, `sc-for`). It has no
bearing on this app.

## Non-negotiables

From the design system's own readme. These are not preferences.

- **One accent.** Action Blue `#0066cc` (`--color-primary`) carries every interactive element.
  `#0071e3` (`--color-primary-focus`) is the hover/focus shade; `#2997ff` is the on-dark variant.
  No second accent colour.
- **Ink is `#1d1d1f`, never pure black.** `#000000` is reserved for the top nav bar and true
  photographic voids.
- **Weight ladder is 300 / 400 / 600 / 700. 500 is deliberately never used.**
- **Exactly one shadow exists in the system** — `rgba(0,0,0,.22) 3px 5px 30px` — and it applies only
  to product photography resting on a surface. **No shadows on cards, buttons, menus or chrome.**
  Elevation is expressed with hairlines and surface colour, not blur.
- **No CSS gradients anywhere.** No repeating patterns or textures.
- **Borders are hairlines.** `rgba(0,0,0,.06)`–`rgba(0,0,0,.14)`, 1px. Dashed borders mean one
  specific thing (see Extensions) and are not decoration.
- **Press state is `transform: scale(0.95)` with no colour shift**, on every button variant.
- **Hover is deliberately unspecified** by the source. Do not invent elaborate hover states; a
  subtle background change on menu rows is the ceiling.
- **No emoji, ever.** No decorative unicode glyphs.
- **Copy is terse and declarative.** Short noun phrases and imperatives. No exclamation points, no
  superlatives, no first person.
- `backdrop-filter: blur()` is functional only — the tab bar floating over content — never
  decorative.

## Tokens

`frontend/src/styles/ds/styles.css` imports all five. New CSS uses `var(--…)`; do not re-type a hex
that already has a token.

| File | Covers |
|---|---|
| `tokens/colors.css` | accent, ink, surfaces, hairlines, the one shadow |
| `tokens/typography.css` | `--font-display` / `--font-text` and the full `--text-*` scale |
| `tokens/spacing.css` | `--space-xxs` 4 → `--space-section` 80, 8px base unit |
| `tokens/radius.css` | `--radius-xs` 5, `sm` 8, `md` 11, `lg` 18, `pill` 9999 |
| `tokens/fonts.css` | loads Inter (see Substitutions) |

**Type.** SF Pro Display for headlines (`--font-display`), SF Pro Text for everything ≤ 20px
(`--font-text`). Display sizes carry negative letter-spacing — the "Apple tight" cadence. Marketing
body is 17px with 1.47 line-height; this app is a dense tool, so it runs its own smaller ladder
(14px table names, 13px values, 12px labels and hints, 11px uppercase eyebrows at `.06em`).

**Spacing.** 8px base unit. Card padding 18–24px, screen padding 24px.

## Radii ladder

| Radius | Used for |
|---|---|
| 0 | full-bleed tiles |
| 5–7px | slot cells, microbtn |
| 8px | compact utility buttons, **dropdown menu options** |
| 10px | text inputs, **dropdown trigger** |
| 11px | pearl-capsule button |
| 12px | **dropdown menu panel**, nested group boxes |
| 18px | cards, modals, panels |
| 9999px | every pill button, chip and badge — the pill is the brand's action signal |

## Component inventory

The design system's bundle (`_ds/…/_ds_bundle.js`) exposes exactly:

`Button`, `IconButton`, `OptionChip`, `ProductTile`, `UtilityCard`, `StickyBar`, `SearchInput`,
`GlobalNav`, `SubNav`.

It **deliberately does not** ship `Select`, `Dialog`, `Tabs`, `Switch`, `Checkbox`, `Radio` or
`Toast` — the source analysis never surfaced them, and the system's rule is not to invent. Where this
app needs one of those, the spec comes from the **canvas file's own component-set screen**, not from
imagination.

The bundle is a canvas-runtime artefact and is not consumed at build time. This app re-implements
what it needs over the vendored tokens:

- CSS classes in `frontend/src/styles/app.css` (`.btn`, `.chip`, `.badge`, `.microbtn`, `.dd`, …)
- thin typed wrappers in `frontend/src/components/ds/`

`ds/Button.tsx` is the reference for that pattern: four variants matching the bundle's, no inline
styles, press state in CSS.

## Control specs

Transcribed from the canvas file. Sizes are literal.

### Button (`.btn`)

| Variant | Background | Foreground | Shape |
|---|---|---|---|
| `primary` | `--color-primary` | `#fff` | pill, 7px 16px |
| `secondary-pill` | `#fff` | `--color-primary` | pill, 1px hairline ring |
| `dark-utility` | `--color-ink` | `#fff` | 8px radius, 8px 14px |
| `pearl-capsule` | `--color-surface-pearl` | `--color-ink` | 11px radius, hairline ring |

Press: `scale(.95)`. Disabled: `opacity .45`.

### Chip (`.chip`) — multi-choice

Pill, `5px 11px`, 12px. Inactive `#fff` + `1px solid rgba(0,0,0,.1)`; active fills
`--color-primary` with white text. **Chips are the design's answer for multi-choice fields** — room
types, teacher pools, group cohorts. Do not replace a chip row with a multi-select dropdown.

### Micro button (`.microbtn`)

7px radius, `4px 10px`, 12px semibold. Idle `#f0f0f2` / `#6e6e73`; active `--color-ink` / `#fff`.

### Badge (`.badge`)

Pill, `3px 9px`, 11px semibold, `.01em`. Tinted per room type; `--plain` is the neutral grey form.

### Dropdown (`.dd`) — single choice

A **button trigger + caret + menu panel**, not a native `<select>`. Native select chrome is
OS-drawn and cannot carry the design; there are no `<select>` elements in this app.

**Trigger** — flex, space-between, gap 8px, full width, `padding: 9px 12px`, `border-radius: 10px`,
`font-size: 14px`, text-align left.

| State | Background | Colour | Border | Ring |
|---|---|---|---|---|
| default | `#fff` | `#1d1d1f` | `1px solid rgba(0,0,0,.14)` | none |
| open | `#fff` | `#1d1d1f` | `1px solid #0066cc` | `0 0 0 3px rgba(0,102,204,.16)` |
| disabled | `#f5f5f7` | `#a1a1a6` | `1px solid rgba(0,0,0,.14)` | none |

**Caret** — a CSS triangle, never a glyph or an icon font. 4px transparent left/right borders with a
`5px` solid top border in `#6e6e73` pointing down, `rgba(0,0,0,.3)` when disabled, or a `5px` bottom
border in `#0066cc` pointing up when open.

**Menu panel** — 6px below the trigger, `padding: 5px`, `border-radius: 12px`, `#fff`,
`1px solid rgba(0,0,0,.08)`, rows separated by a 1px gap. **No shadow.**

**Option row** — flex, space-between, `padding: 8px 10px`, `border-radius: 8px`, `font-size: 13.5px`.
Selected: `#e9f1fb` fill, `#0a4f9e` text, weight 600, with a right-aligned 12px `#0066cc` semibold
"Selected" label. Unselected: transparent, `#1d1d1f`, weight 400.

### Text input

`padding: 9px 12px`, `border-radius: 10px`, `1px solid rgba(0,0,0,.14)`, `#fff`, 14px. Focus moves
the border to `--color-primary`. Same geometry as the dropdown trigger — they sit in the same forms
and must line up.

### Entity form field

12px semibold label in `#3a3a3c`, 6px gap, control, then an 11.5px `#86868b` hint at 1.45
line-height. Primary + `secondary-pill` buttons in the footer.

### Card, table, session card

Card: `#fff`, `1px solid rgba(0,0,0,.06)`, 18px radius, no shadow. Table: 11px uppercase `.04em`
headers on parchment, 14px semibold name cells, 13px `#6e6e73` value cells, `#f0f0f0` row rules.
Session card: subject-tinted fill, 3px colour spine, 12.5px semibold subject; soft conflict adds a
dashed edge and an amber marker; selected is a white fill with a 2px Action Blue ring.

## Extensions

Things this app needs that the design project does not document. They are listed here so the line
between "derived" and "invented" stays visible.

- **`.dd--sm`** — the dropdown at 13px / `6px 10px` / 8px radius, for the dense inline rows
  (semester editors, week navigation). The canvas file documents only the field size.
- **`.dd__menu` is portalled and `position: fixed`.** The canvas file positions the panel
  `absolute` inside the field. The real modal is `max-height: 86vh; overflow-y: auto`, which would
  clip it, so the panel renders in a portal at a computed rect and flips above the trigger when
  there is no room below. Visually identical to the spec.
- **`.chip--disabled`** — a group that has no term dates for the semester its chip row belongs to.
  Uses the disabled-dropdown values: parchment `#f5f5f7` fill, `#a1a1a6` ink, solid hairline.
- **Dashed borders** appear only on the soft-conflict session card and blocked slot cells. Do not
  reach for a dashed border to mean "disabled" or "empty".
- **`.sesscard--more`** — a grid cell shows at most **two** session cards (`SHOWN_PER_CELL` in
  `ResultScreen.tsx`); the rest collapse into one `+ N more` card. It is a control, not a session,
  so it takes parchment fill, `#6e6e73` text and no subject tint or colour spine. The copy is a
  count, no names — the design's copy is terse. The threshold is the same in both densities: how
  much the grid hides must not depend on a display toggle. The design project's grid loops its
  sessions uncapped and documents no overflow affordance.
- **`.modal--fixed` + `.modal__scroll`** — the overflow dialog is a **constant** 520px (capped at
  `86vh`), so a period with three sessions and one with thirty open the same box; the list inside is
  what scrolls. Chrome — backdrop, 18px radius, hairline, `Close` link — is inherited from the entity
  modal; no shadow is added. The design project documents no dialog at all.
- **`.progress` / `.progress__fill`** — a determinate sibling of the mock's `.sweep`, same geometry
  (4 px, pill radius, `--color-primary` on `#f0f0f2`) so the two read as one control in two states:
  the sweep while there is nothing to count, the bar once the solver has said how many phases the
  run has. The canvas file documents only the indeterminate sweep.
- **`.accordion__aside` / `.runlist` / `.runrow__*`** — the Generate screen lists one accordion row
  per solve, with its status and live progress in the summary row and its full result in the body.
  The canvas file shows a single run panel and no accordion outside the settings dialog.
- **`.stalebar`** — the banner over a timetable generated before the input data changed. Uses the
  app's amber warn palette (`#fdf6ee` on `#8a4408`) with a **solid** hairline: dashed edges are
  reserved for soft conflicts and blocked slots, and a stale timetable is neither.
- **`.daytoggles` / `.daytoggle`** — the Mon–Sun row above the slot grid; a weekday is switched on or
  off there rather than added and removed from the end of the week. On reuses the grid's own
  teaching palette (`#e9f1fb` on `rgba(0,102,204,.35)`), off reuses the blocked palette (`#f5f5f7` on
  `#c7c7cc`) but with a **solid** hairline — dashed edges are reserved for soft conflicts and blocked
  cells, and a weekday nobody teaches on is neither. Capsule radius and the standard `scale(0.95)`
  press. The canvas file draws the slot grid as a fixed Mon–Fri week with no control over it.
- **`.slotgrid__times` / `.slotgrid__time` / `.slotgrid__rowhead--bad` / `.slotgrid__err`** — period
  start and end are four `.dd--sm` dropdowns in the grid's row head: hour and minute per end, the
  pair at a 3px gap and the two ends at 7px, so a time still reads as one value. `input[type=time]`
  drew this first and drew it wrong — the format is the viewer's locale's to choose, so it rendered
  `08:00 AM` with a clock glyph from an icon set this app does not own. The option labels are ours,
  so the clock is always 24-hour; this is the **Dropdown** rule ("native select chrome is OS-drawn
  and cannot carry the design") applied to the other native picker. Minutes step by a quarter hour,
  widened to hold an off-grid value when the stored problem has one, since a `Select` whose value
  matches no option would fall back to its placeholder and hide a real time. A period whose times
  would overlap its neighbour keeps what was picked, takes a `#7d1f1f` trigger border and shows the
  reason underneath at 11px in the same colour — the app's bad-status colour, used here as inline
  validation rather than as a status. The canvas file renders period times as static text.
- **`input[type=date]` stays native**, in `CourseDatesEditor.tsx` and the offering editor's spread
  window and изпитна дата. A date picker is a month
  grid, not a list, and the design project documents no such panel — there is nothing here to derive
  it from, and inventing one would be a bigger departure than the OS calendar is. Dropdowns and time
  pickers have a documented answer and must use it.
- **`.sesscard--clash` / `.sesscard__clashflag` / `.sesscard--dragging` / `.grid__cell--drop` /
  `.penalty--bad`** — the timetable can be edited by hand: a session is dragged to another cell, or
  moved through a dialog. A move that breaks a hard rule is accepted and then flagged, so a card
  needs a treatment stronger than the soft-conflict one it may already be wearing. The clash ring is
  the **same ring shape `.sesscard--selected` uses**, in `#7d1f1f` instead of Action Blue, and
  **solid** — dashed edges are reserved for soft conflicts and blocked cells. Its marker is a disc
  where the soft marker is a triangle, because both can sit on one card. A card selected *and*
  clashing takes both rings, red inside blue. The drop target reuses the slot grid's teaching pair
  (`#e9f1fb` on `rgba(0,102,204,.35)`), as an inset ring so the cell does not shift under the cursor.
  `.penalty--bad` is the detail panel's amber `.penalty` block in the bad-status palette. The canvas
  file's grid is read-only and documents no drag affordance at all.
- **`.slotgrid__break`** — the gap the period times leave between two periods, drawn as a
  warn-tinted rule between the rows it sits between. It exists because the обедна почивка is
  otherwise *invisible*: nothing marks it in the data, because nothing enforces it — it is simply a
  stretch of clock no period covers. A break you cannot see is a break somebody will delete by
  accident.
- **`.prefgrid--hard`** — the availability grid is not the preference grid. A selected preference
  cell is a dashed Action-Blue outline (soft, and dashed means soft everywhere in this app); a
  selected availability cell is a **solid** `#1f7a3d` outline on the ok tint, because hard
  availability is not something the objective can trade away. The two grids sit one above the other
  in the teacher form and have to be told apart at a glance.
- **`.sesscard__marker`** — the activity marker (л / у / п) beside the subject code on a session
  card, at regular weight in `#6e6e73` so it reads as an annotation on the code rather than part of
  it. It is what the printed разписание puts in its grid cells, and the card echoes it.
- **`.offering` / `.offering__grid` / `.offering__head`** — the учебен план form is two forms in one
  (лекции and упражнения are almost different subjects), separated by eyebrow headings over a
  hairline rather than by boxes or cards: they are one form, and boxing them would say otherwise.
  `.offering__grid` is the auto-fit row the хорариум's three numbers sit in.
- **`.razp__frame`** — the printed разписание is rendered server-side as a complete HTML document
  with its own `@page` rules, so it is shown in a sandboxed iframe rather than spliced into this
  page. The frame is a 12px-radius hairline box on white; nothing inside it is styled from here.
- **`.dot`** — an 8px colour disc before a subject's name in the catalogue and учебен план tables,
  carrying the same `subjectColor` the session cards use. The design's tables have no colour column,
  and a badge would be too heavy for a row that already carries a code and a name.
- **Status colours** (`#1f7a3d` ok, `#8a4408` warn, `#7d1f1f` bad and their tints) are an app
  addition; the source system has no semantic status palette.

## Substitutions to preserve

- **Inter stands in for SF Pro.** SF Pro is Apple-proprietary and no files were provided;
  `tokens/fonts.css` loads Inter from Google Fonts, and `system-ui, -apple-system` in the stack still
  resolves to real SF Pro on Apple platforms. Keep both in every font stack.
- **Icons are placeholders.** The source documents icons by role, not by asset. Prefer CSS shapes
  (the dropdown caret is a triangle, not an icon) over pulling in an icon library.
- **No Apple logo or wordmark is ever drawn.** This app has its own name and does not carry Apple
  branding.
