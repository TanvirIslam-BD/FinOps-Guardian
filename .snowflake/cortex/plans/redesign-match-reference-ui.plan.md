---
name: "redesign-match-reference-ui"
created: "2026-07-27T09:02:15.373Z"
status: pending
---

# Plan: Redesign to Match Reference UI

## Overview

Rewrite the Streamlit app's UI to match the polished reference design screenshot. This involves updating CSS, replacing `st.metric` calls with custom HTML cards, adding card containers around charts, and refining the sidebar navigation.

## Key Design Elements from Reference

### Sidebar

- Logo icon + "FinOps Guardian" inline (horizontal, not stacked vertically)
- Subtitle "AI-POWERED COST INTELLIGENCE" in small caps below
- Two mini status cards side-by-side (Open Issues with red number, Unread with blue number)
- "View Notifications →" as a subtle link/button
- "NAVIGATION" section header label
- Nav items with **indigo left-border** on active item (not radio buttons — but we'll style the radio to look like this)
- "AGENT CONTROLS" section with scan buttons
- Reset Demo expander
- Footer with version

### Main Content - Page Header

- Page title with emoji on left
- Date range text "Jul 20 – Jul 26, 2025" (computed from current week)
- "Refresh" button on right side

### KPI Cards (5 in a row)

Each card has:

- Small colored circle icon (red triangle for anomalies, orange coins for credits, green dollar for savings, blue clipboard for issues, green leaf for CO2)
- Uppercase small label text
- Large bold value
- Green/red delta text like "↑ 2 vs last 7 days"

### Charts Section

- Two side-by-side in bordered card containers
- Card has a header row with title + info icon + dropdown (USD / Last 7 Days)
- Clean border-radius, subtle shadow

### Warehouse Health Scores

- Section header "Warehouse Health Scores" with "View all warehouses →" link

- Cards showing:

  - Warehouse name with green/yellow/red dot indicator
  - Score "85/100" large text
  - "Healthy" badge in green (or "Needs Attention" in yellow, etc.)
  - Progress bar (green fill to score%)
  - Delta "↑ 5 vs last 7 days"

### Footer

- "All times shown in your local timezone" with ℹ️ icon

## Implementation Approach

Since we're on SiS (Streamlit \~1.22), everything visual beyond basic widgets must be done via `st.markdown()` with `unsafe_allow_html=True`. We'll:

1. **CSS**: Write a comprehensive CSS block that styles radio buttons to look like nav items with left-border active state, card containers, progress bars, etc.
2. **HTML Cards**: Create Python helper functions that generate HTML strings for KPI cards, health cards, chart wrappers, etc.
3. **Layout**: Use `st.columns()` for the grid, but render content inside as styled HTML.

## Constraints

- No `st.container(border=True)` (SiS limitation)
- No `color=` param on `st.bar_chart`
- Use `st.experimental_rerun()` not `st.rerun()`
- No `hide_index` in `st.dataframe()`
- Python 3.11, Streamlit \~1.22
