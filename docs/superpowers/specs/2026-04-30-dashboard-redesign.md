# GAWorld Dashboard Redesign — Editorial Monitoring Style

## Goal

Redesign the GAWorld dashboard from a generic dark monitoring console into an editorial/magazine-style monitoring panel — warm, readable, and visually intentional while maintaining full information density.

## Architecture

Pure CSS + Chart.js config changes. No HTML structure changes (except adding a left agent list which is already done). No new dependencies. The redesign is achieved entirely through:

- CSS variable replacement (color system)
- Typography adjustments (font stack, sizes, weights)
- Spacing and border refinements
- Chart.js option overrides (colors, fonts, grid styles)

## Design Direction

**Style:** Editorial / magazine aesthetic applied to a monitoring dashboard
**Emotional tone:** Warm, professional, calm — like a well-designed print journal
**One thing user should remember:** "This feels like a premium data publication, not a generic dashboard"

## Visual System

### Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#f4f1ea` | Page background — warm off-white |
| `--surface` | `#fdfaf5` | Card/panel surface — warm white |
| `--surface-2` | `#f7f3ec` | Secondary surface (inputs, hover) |
| `--border` | `#d4cdc0` | Borders and dividers |
| `--border-light` | `#e0d9cc` | Lighter borders |
| `--text` | `#2e2826` | Primary text — deep warm brown |
| `--text-muted` | `#8a7e6e` | Secondary text |
| `--navy` | `#1f3a4b` | Primary accent — masthead, buttons, headers |
| `--teal` | `#2b5e6b` | Secondary accent |
| `--gold` | `#c8a96e` | Decorative accent — badges, highlights |
| `--red` | `#c65d3a` | Danger, negative values, errors |
| `--green` | `#4a7c5e` | Positive values, active indicators |
| `--code-bg` | `#1a1f1c` | Code block background |
| `--shadow` | `0 4px 20px rgba(47, 40, 36, 0.08)` | Card shadow |

### Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| H1 (page title) | Georgia, serif | 36px | 700 |
| H2 (section title) | Georgia, serif | 20px | 700 |
| H3 (sub-section) | System sans-serif | 13px | 700 |
| Kicker label | System sans-serif | 11px | 800, uppercase |
| Body / data | System sans-serif | 13px | 400 |
| Data values (numeric) | Monospace | 18-22px | 900 |
| Code | Monospace | 12px | 400 |
| Buttons | System sans-serif | 13px | 700 |

### Layout

Keep the existing workspace grid (3-column on wide screens, 1-column on narrow). Key refinements:

- **Masthead:** Navy background (#1f3a4b) with white text, replaces current dark green
- **Agent list:** Left sidebar with neutral backgrounds, navy highlight for selected
- **Map panel:** Centered with subtle shadow
- **Right stack:** Cards with warm white surfaces, navy section dividers
- **Lower grid:** Economy + memory + run log in editorial card layout

### Component Styles

**Buttons:**
- Default: warm surface background (`--surface-2`), warm border (`--border`), body text (`--text`). Hover: darker background (`--border`), lighter border (`--border-light`)
- Primary: navy background, white text
- Danger: red background, white text
- Small variant for toolbar buttons

**Code blocks:**
- Dark background (#1a1f1c) contrast against warm white cards
- Green-tinted monospace text for readability

**Charts (Chart.js overrides):**
- Grid lines: muted warm gray
- Labels: warm brown text
- Tooltips: warm surface background
- Radar fill: translucent warm tones
- Economy line colors: teal for balance, gold for income, red for expense

**Agent list:**
- Selected item: navy left border accent, light navy background tint
- Active dot: teal green with subtle glow
- Number: muted warm gray

### Responsive

- 1280px breakpoint: collapse to single column
- 720px breakpoint: tighter padding, smaller masthead text

## Out of Scope

- No changes to HTML structure (beyond the already-added left agent list)
- No JavaScript functionality changes
- No new external dependencies or fonts
- No backend changes
- No dark mode (this is a warm light theme by design)

## Files Changed

| File | Change |
|------|--------|
| `site/dashboard/styles.css` | Full rewrite — new color system, typography, spacing, component styles |
| `site/dashboard/charts.js` | Update Chart.js color options to match new palette |
