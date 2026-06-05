# Dashboard Redesign — Editorial Magazine Style

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the GAWorld dashboard from a dark console theme to a warm editorial/magazine-style monitoring panel.

**Architecture:** Pure CSS variable replacement + Chart.js color options update. No HTML or JS logic changes. The layout structure (3-column grid, agent list, panels) stays identical — only colors, typography, spacing, and visual treatments change.

**Tech Stack:** CSS custom properties, Chart.js 4.x, vanilla JS

---

### Task 1: Rewrite styles.css with editorial magazine theme

**Files:**
- Modify: `site/dashboard/styles.css` (full rewrite — all 600 lines)

- [ ] **Step 1: Replace CSS variables with new editorial color system**

Replace the `:root` block with the new palette:
- `--bg`: `#f4f1ea` (warm off-white page background)
- `--surface`: `#fdfaf5` (warm white card surface)
- `--surface-2`: `#f7f3ec` (slightly darker surface for inputs/hover)
- `--border`: `#d4cdc0` (subtle warm border)
- `--border-light`: `#e0d9cc` (lighter border)
- `--text`: `#2e2826` (deep warm brown for body text)
- `--text-muted`: `#8a7e6e` (muted warm brown)
- `--navy`: `#1f3a4b` (primary accent — mastheads, buttons, headers)
- `--teal`: `#2b5e6b` (secondary accent)
- `--gold`: `#c8a96e` (decorative accent — badges, highlights)
- `--red`: `#c65d3a` (danger, negative values)
- `--green`: `#4a7c5e` (positive values, active dots)
- `--code-bg`: `#1a1f1c` (code block background — stays dark for contrast)
- `--shadow`: `0 4px 20px rgba(47, 40, 36, 0.08)` (soft warm shadow)
- `--ease`: `cubic-bezier(0.16, 1, 0.3, 1)` (keep same easing)

- [ ] **Step 2: Update body and masthead**

Body: warm off-white background (`#f4f1ea`), warm brown text (`#2e2826`), remove green radial gradients, remove `SF Pro Display` from font stack (keep `"Aptos", "Noto Sans SC", "Microsoft YaHei", sans-serif`).

Masthead: `background: var(--navy)`, header title in `Georgia` serif with `#fdfaf5` (warm white) text. Kicker badge: `background: rgba(200, 169, 110, 0.15)`, `color: var(--gold)`. Description text: `rgba(253, 250, 245, 0.65)`.

Masthead image border: `border-left: 1px solid rgba(253, 250, 245, 0.12)`.

Masthead-copy: remove green gradient, use `background: var(--navy)`.

- [ ] **Step 3: Update toolbar and form controls**

Toolbar: `background: var(--surface)`, `border-color: var(--border)`. Labels use `color: var(--text-muted)`.

Inputs/selects/textareas: `background: var(--surface-2)`, `border-color: var(--border)`, `color: var(--text)`. Focus state: `border-color: var(--navy)`, `box-shadow: 0 0 0 3px rgba(31, 58, 75, 0.1)`.

Checkline: `background: var(--surface-2)`, hover `border-color: var(--border-light)`. Accent color: `var(--navy)`.

- [ ] **Step 4: Update buttons**

Default button: `background: var(--surface-2)`, `border-color: var(--border)`, `color: var(--text)`. Hover: `background: var(--border)`, `border-color: var(--border-light)`.

Primary button: `background: var(--navy)`, `color: #fdfaf5`, `border-color: var(--navy)`. Hover: `background: #2a4d62`, remove green glow.

Danger button: `background: var(--red)`, `color: #fdfaf5`, `border-color: var(--red)`. Hover: `background: #d46a48`.

Small button: keep same dimensions.

- [ ] **Step 5: Update panel/section-head/status-line**

Panel: `background: var(--surface)`, `border-color: var(--border)`, `border-radius: 8px` (was 10px).

Section-head kicker: `color: var(--teal)` (was accent/green).

Section-head h2: use Georgia for serif editorial feel.

Status badges: `background: var(--surface)`, `border-color: var(--border)`. Running: `color: var(--green)`, `border-color: rgba(74, 124, 94, 0.3)`, green dot. Done: `color: var(--green)`. Error: `color: var(--red)`, red dot.

- [ ] **Step 6: Update agent list**

Selected item: `border-color: var(--navy)`, `background: rgba(31, 58, 75, 0.06)`. Selected `.agent-id`: `color: var(--navy)`.

Active dot: `background: var(--green)`, `box-shadow: 0 0 6px var(--green)`.

- [ ] **Step 7: Update map, timeline, code blocks**

Map canvas: `background: #e8e4db` (warm light), `border-color: var(--border)`.

Timeline range slider: `background: var(--border)`. Thumb: `background: var(--navy)`, `border-color: var(--surface)`.

Code blocks: keep dark background (`--code-bg: #1a1f1c`), text `#c5ddd4` (green-tinted monospace). `border-color: var(--border)`.

- [ ] **Step 8: Update economy/perf/radar legend components**

Econ card: `background: var(--surface-2)`, `border-color: var(--border)`. Positive: `color: var(--green)`. Negative: `color: var(--red)`.

Perf card: same pattern as econ card.

Radar legend item: `color: var(--text-muted)`.

- [ ] **Step 9: Update responsive & scrollbar**

At 1280px: `workspace` collapses to 1 column. Everything else unchanged from existing structure.

At 720px: tighter padding, smaller header.

Scrollbar: `background: var(--border)` thumb, transparent track. Keep existing.

- [ ] **Step 10: Update placeholder text and global h1/h2/h3**

H1: `font-family: Georgia, serif`, `color: var(--text)`. H2: `font-family: Georgia, serif`, `color: var(--text)`. H3: `color: var(--text-muted)`.

Placeholder text: `color: var(--text-muted)`.

- [ ] **Step 11: Commit**

```bash
git add site/dashboard/styles.css
git commit -m "refactor: redesign dashboard with editorial magazine style

Warm off-white background, navy/teal/gold accent palette,
Georgia serif headings, refined spacing and component styles."
```

### Task 2: Update Chart.js colors for new palette

**Files:**
- Modify: `site/dashboard/charts.js`

- [ ] **Step 1: Update radar chart colors**

Replace `RADAR_COLORS`:
```
border: "rgba(31, 58, 75, 0.8)"       → navy
background: "rgba(31, 58, 75, 0.08)"   → navy transparent
point: "rgba(31, 58, 75, 1)"           → navy solid
```

Replace `MULTI_AGENT_COLORS`:
1. Navy `rgba(31, 58, 75, ...)`
2. Terracotta `rgba(198, 93, 58, ...)`
3. Teal `rgba(43, 94, 107, ...)`
4. Gold `rgba(200, 169, 110, ...)`
5. Olive `rgba(109, 125, 86, ...)`
6. Mauve `rgba(146, 116, 138, ...)`
7. Slate `rgba(100, 115, 125, ...)`

All use `0.8` / `0.08` / `1.0` pattern for border/background/point.

- [ ] **Step 2: Update radar scale options**

Grid: `color: "rgba(212, 205, 192, 0.6)"` (warm border tone)
Angle lines: same
Point labels: `color: "#2e2826"` (warm brown)
Ticks: `color: "#8a7e6e"` (muted brown)

- [ ] **Step 3: Update economy chart colors**

`ECONOMY_COLORS`:
- balance: `border "rgba(74, 124, 94, 0.9)"`, `background "rgba(74, 124, 94, 0.06)"`
- income: `border "rgba(200, 169, 110, 0.9)"`, `background "rgba(200, 169, 110, 0.06)"`
- expense: `border "rgba(198, 93, 58, 0.9)"`, `background "rgba(198, 93, 58, 0.06)"`

- [ ] **Step 4: Update economy chart scale options**

Grid lines: `color: "rgba(212, 205, 192, 0.5)"`
X/Y axis ticks: `color: "#8a7e6e"`
Axis title: `color: "#2e2826"`
Legend labels: `color: "#2e2826"`

- [ ] **Step 5: Update point border colors**

Replace `pointBorderColor: "#141a18"` (dark theme) with `pointBorderColor: "#fdfaf5"` (warm white to match new card surfaces).

- [ ] **Step 6: Commit**

```bash
git add site/dashboard/charts.js
git commit -m "refactor: update Chart.js colors for editorial palette

Navy/teal/gold/terracotta color scheme for radar and economy charts,
warm-toned grid lines and labels."
```

### Task 3: Integration check

- [ ] **Step 1: Start dashboard and verify**

```bash
# Kill old server, start fresh
pkill -f dashboard_server.py 2>/dev/null; sleep 0.5
python dashboard_server.py --port 8767
```

- [ ] **Step 2: Open browser and verify**

Open `http://localhost:8767/dashboard/`

Verify checklist:
- [ ] Masthead has navy background, white serif title, gold kicker badge
- [ ] Page background is warm off-white
- [ ] All panels have warm white surfaces with warm gray borders
- [ ] Agent list items highlight with navy on select
- [ ] Inputs/buttons use warm tones, navy focus rings
- [ ] Code blocks remain dark (contrast against warm cards)
- [ ] Radar chart uses navy/teal/gold colors on warm background
- [ ] Economy chart: green balance, gold income, red expense
- [ ] Status badges show correct colors (green running, red error)
- [ ] Responsive: narrow browser to 1280px → single column
- [ ] Responsive: narrow browser to 720px → tighter layout

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/ -q --tb=short
```

Expected: same result as before (108 passed, 2 pre-existing failures in test_memory_recall_and_review.py).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: integration check and final adjustments"
```
