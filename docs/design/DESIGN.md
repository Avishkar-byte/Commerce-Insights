---
name: Calm Logistics Rigor
colors:
  surface: '#f8f9ff'
  surface-dim: '#d0daee'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff3ff'
  surface-container: '#e6eeff'
  surface-container-high: '#dfe9fc'
  surface-container-highest: '#d9e3f7'
  on-surface: '#121c2a'
  on-surface-variant: '#424751'
  inverse-surface: '#273140'
  inverse-on-surface: '#ebf1ff'
  outline: '#727782'
  outline-variant: '#c2c6d3'
  surface-tint: '#1d5eac'
  primary: '#00478c'
  on-primary: '#ffffff'
  primary-container: '#1f5fad'
  on-primary-container: '#c8dbff'
  inverse-primary: '#a8c8ff'
  secondary: '#555f71'
  on-secondary: '#ffffff'
  secondary-container: '#d6e0f5'
  on-secondary-container: '#596375'
  tertiary: '#005333'
  on-tertiary: '#ffffff'
  tertiary-container: '#006e44'
  on-tertiary-container: '#8befb6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d6e3ff'
  primary-fixed-dim: '#a8c8ff'
  on-primary-fixed: '#001b3d'
  on-primary-fixed-variant: '#00468a'
  secondary-fixed: '#d9e3f8'
  secondary-fixed-dim: '#bdc7db'
  on-secondary-fixed: '#121c2b'
  on-secondary-fixed-variant: '#3d4758'
  tertiary-fixed: '#93f7bd'
  tertiary-fixed-dim: '#77daa3'
  on-tertiary-fixed: '#002111'
  on-tertiary-fixed-variant: '#005232'
  background: '#f8f9ff'
  on-background: '#121c2a'
  surface-variant: '#d9e3f7'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  code-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-dense: 0.5rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system serves an empirical, research-grade analytics environment engineered for analyzing Brazilian freight networks, multi-year marketplace trends, and operational delivery vectors. The audience consists of supply-chain researchers, econometricians, and senior logistics planners who require sustained visual stamina during extended data inspection sessions.

The design philosophy adopts a strict **flat, academic functionalism**. It treats the viewport not as a dynamic marketing surface, but as an interactive digital ledger and research instrument. The emotional posture is disciplined, sober, dependable, and quietly authoritative.

Key principles:
- **Zero ornamentation:** No blur filters, ambient diffusion, decorative gradients, or emotive iconography. Every visual mark represents either a dimension, a metric, or a structural boundary.
- **Typographic restraint:** Absolute adherence to sentence case across all headings, metric labels, statuses, and table headers. All-caps styling and decorative emojis are explicitly prohibited to maintain academic rigor.
- **Cartographic clarity:** Color is reserved strictly for operational meaning, data differentiation, and geographic/delivery delay states. Structural UI remains monochromatic and neutral.

## Colors

The palette operates under a high-legibility light model with precise contrast ratios optimized for information density, tabular scanning, and choropleth/freight visualization.

### Surface and Canvas
- **Paper Canvas (`#FFFFFF`):** Base canvas for analytical modules, data cards, and viewport workspaces.
- **Mist Surface (`#EEF2F6`):** Applied to persistent navigation, the secondary filter sidebar, table headers, and structural backgrounds behind paper panels.
- **Structural Border (`#DDE3EA`):** A hairline divider used to separate cells, cards, panels, and toolbars without visual weight.

### Typography & Structure
- **Text Ink (`#16213E`):** Primary reading ink for metrics, data tables, and major headings. Provides optimal blackbody-style legibility against `#FFFFFF` and `#EEF2F6`.
- **Muted Secondary (`#5B6577`):** Analytical metadata, column headers, units of measurement, axis markers, and secondary notes.
- **Neutral Context (`#8A94A6`):** Inactive controls, placeholder inputs, empty-state borders, and contextual baseline gridlines in charts.

### Brand & Focus Action
- **Route Blue (`#1F5FAD`):** The primary interaction driver and primary operational series. Used for active navigation selections, focus indicators, default chart vectors, links, and baseline order flows.

### Semantic Delivery Scale
Used exclusively for tracking actual vs. estimated arrival deltas, delivery performance cohorts, and SLA breach models. It must never be applied to generic UI controls:
- **Optimal (`#1E8A5A`):** Delivered well ahead of SLA / on schedule.
- **Tolerable (`#D9A21B`):** Minor buffer reduction (1–2 days remaining).
- **At Risk (`#D9731B`):** Impending breach or minor delay.
- **Breached (`#C2451E`):** Verified carrier delay beyond promised window.
- **Critical Failure (`#8F1D14`):** Severe breach, lost parcels, or operational dead-ends.

## Typography

The type scale is constrained strictly to five base steps: 28px, 20px, 16px, 14px, and 12px. The single typeface family `Inter` provides high legibility at micro scales with crisp letterforms and open apertures suited for dense logistics tables and coordinate listings.

### Scale Rules
- **28px (Headline Lg):** Primary view titles, executive logistics summaries, and total order volume KPIs.
- **20px (Headline Md):** Panel clusters, regional breakdown section headers, and secondary metric calls.
- **16px (Title Md):** Card container headers, module titles, and modal titles.
- **14px (Body Md / Label Md):** Default data tables, analytical filters, form controls, primary body text, and button labels.
- **12px (Body Sm / Label Sm / Code Sm):** Axis values, micro-metadata (order IDs, CEP zip prefixes, UTC timestamps), table headers, and status badges.

### Formatting Rules
- Always use sentence case for every label, button, column heading, and title.
- Do not use uppercase letter-spacing (tracking) or capitalized acronym transformations unless displaying ISO codes (e.g., `BRL`, `SP`, `RJ`).
- Numeric metrics and tabular coordinates must enforce tabular lining figures (`font-variant-numeric: tabular-nums`) to prevent horizontal jitter during data refreshes.

## Layout & Spacing

The layout model utilizes a structured, boundary-aligned fluid canvas split across operational zones:
1. **Persistent Operational Sidebar (240px fixed width):** Sits on the Mist background (`#EEF2F6`) housing dataset partition selectors (state filtering, delivery timelines, category segments).
2. **Global Parameter Strip (48px fixed height):** Anchors date range pickers (2016–2018 bounds) and baseline comparisons.
3. **Data Grid Workspace (Fluid):** A 12-column layout running a 16px (`1rem`) gutter and 24px (`1.5rem`) outer margin.

### Density Tiers
- **Comfortable View (Default):** Metric dashboards and distribution charts utilize `space-lg` (16px) internal card padding and `space-md` (12px) element spacing.
- **Dense Analytical View (Data Tables & Matrix Views):** Table cell padding shifts to `space-xs` (4px) vertical by `space-sm` (8px) horizontal, with a reduced `gutter-dense` (8px) between contiguous metric cells.

### Responsive Reflow
- **Desktop (1280px and above):** Dual-pane or triple-pane operational layouts (sidebar, master analytical list, map/detail view).
- **Tablet (768px – 1279px):** Sidebar collapses to an icon-and-label drawer; 12-column workspace reorganizes into paired 6-column operational cards.
- **Mobile (< 768px):** Linear stacked view with horizontally scrollable data tables; charts shift to sparkline summaries with tabbed breakdown cards.

## Elevation & Depth

This design system completely eliminates ambient drop shadows, multi-tier directional lighting, and frosted glass/blur treatments. Depth and hierarchy are achieved entirely through **flat surface containment** and **chromatic differentiation**.

### Architectural Elevation Layers
1. **Level 0 (Base Substrate):** `#EEF2F6` (Mist). Serves as the deep structural underlay visible in gaps, toolbars, sidebars, and viewport dividers.
2. **Level 1 (Working Surface):** `#FFFFFF` (Paper). Applied to functional cards, analytical tables, chart containers, and modal bodies. Every Level 1 surface is bounded by a 1px solid `#DDE3EA` outline.
3. **Level 2 (Transient Overlays & Dropdowns):** `#FFFFFF` with a 1px solid `#16213E` border (or a high-contrast `#8A94A6` border) and a single flat 2px offset border line (`box-shadow: 0 2px 0 0 #DDE3EA`). No blur.

### Boundary Contrast
Containers rely on structural proximity and 1px `#DDE3EA` borders. When two interactive panels touch, a 1px border is preferred over a gap to preserve analytical screen real estate.

## Shapes

The design system enforces an understated, utilitarian shape system capped at a strict maximum corner radius of 8px. This geometry complements structural grid alignments, tabular columns, and rectangular data cards.

### Corner Radius Tokens
- **Sharp Base (0px):** Data table cells, split-segment controls, inline data visualizer bars, and full-bleed drawer edges.
- **Default Soft (`rounded`: 4px):** Standard inputs, operational buttons, status chips, tooltips, checkboxes, and select menus.
- **Container Soft (`rounded-lg`: 8px):** Analytical cards, dialogs, map overlays, and workspace panels. Radius must never exceed 8px.

## Components

### Buttons & Operational Actions
- **Primary Button:** Solid Route Blue (`#1F5FAD`) background, white (`#FFFFFF`) text, 4px border radius, 32px height for dense contexts, 36px for default contexts. No shadow. Hover: `#184B8A`. Focus: 2px solid `#16213E` with 2px offset.
- **Secondary Button:** White (`#FFFFFF`) background, 1px solid `#DDE3EA` border, Text Ink (`#16213E`) text. Hover: `#EEF2F6` background with `#8A94A6` border.
- **Tertiary/Ghost Action:** Transparent background, Route Blue (`#1F5FAD`) text, underline only on hover. Used for auxiliary table operations (e.g., "export rows", "reset filter").

### Chips & Badges
- **Analytical Chips:** Used for active filters. Background `#EEF2F6`, border 1px solid `#DDE3EA`, text `#16213E`, font size 12px, radius 4px. Trailing "x" icon in `#5B6577`.
- **Delivery Delay Badges:** Strict 4px radius pill containing a 6px circular dot indicator. Background is a 10% tint of the delay color, text is the full-saturation delay scale hex code (e.g., `#1E8A5A` for early, `#8F1D14` for severe delay). All text in sentence case: "On schedule", "Slight delay", "Breached".

### Data Tables
- **Header:** `#EEF2F6` background, 32px height, 1px solid `#DDE3EA` bottom border. Text in `#5B6577`, 12px, font-weight 500, sentence case.
- **Row:** `#FFFFFF` background, 36px default height (28px in compact mode), 1px solid `#DDE3EA` bottom border. Text in `#16213E`, 14px (12px for codes/IDs). Hover state: `#F5F8FA` background.
- **Selected Row:** `#EEF2F6` background with a 2px vertical left accent line in `#1F5FAD`.

### Form Controls & Filter Selectors
- **Text Inputs & Dropdowns:** 32px height, white background, 1px solid `#DDE3EA` border, 4px radius, 14px text. Focus state switches border to `#1F5FAD` with zero glow.
- **Checkboxes & Radios:** 16px square/circle, 1px solid `#8A94A6` border. Checked state uses solid `#1F5FAD` fill with a crisp white mark. Radius for checkbox is 2px.

### Cards & Analytical Panels
- **Structure:** Level 1 `#FFFFFF` background, 1px solid `#DDE3EA` border, 8px radius, padding 16px.
- **Card Header:** Title in 16px font-weight 600 `#16213E`. Optional metadata/unit displayed in 12px `#5B6577` aligned right.

### Metric KPI Tiles
- Single metric card containing:
  - Metric label: 12px, sentence case, `#5B6577`.
  - Primary metric value: 28px font-weight 600, `#16213E`, tabular numerals.
  - Comparative benchmark (e.g., "vs prior 90 days"): 12px text in `#5B6577` with directional baseline delta.