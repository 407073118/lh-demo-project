---
version: alpha
name: Institutional Quant Console
description: A high-density research console for LH Quant, tuned for A-share backtesting, auditability, and repeated analysis.
colors:
  platform-rail: "#0b1220"
  platform-nav: "#172033"
  platform-ink: "#101828"
  background: "#eef3f8"
  surface: "#ffffff"
  surface-muted: "#f6f8fb"
  surface-data: "#fbfcf8"
  border: "#d3dce8"
  border-subtle: "#e7edf4"
  gridline: "#e6edf5"
  text: "#172033"
  text-muted: "#5f6f84"
  primary: "#1f6feb"
  primary-strong: "#1554b7"
  buy: "#c92a1f"
  sell: "#027a48"
  warning: "#8a4b0f"
  danger: "#b42318"
typography:
  display:
    fontFamily: Microsoft YaHei UI
    fontSize: 22px
    fontWeight: "800"
    lineHeight: 28px
  title:
    fontFamily: Microsoft YaHei UI
    fontSize: 14px
    fontWeight: "800"
    lineHeight: 20px
  body:
    fontFamily: Microsoft YaHei UI
    fontSize: 13px
    fontWeight: "500"
    lineHeight: 20px
  label:
    fontFamily: Microsoft YaHei UI
    fontSize: 12px
    fontWeight: "700"
    lineHeight: 16px
  mono:
    fontFamily: Cascadia Mono
    fontSize: 12px
    fontWeight: "500"
    lineHeight: 20px
rounded:
  sm: 5px
  md: 8px
  pill: 999px
spacing:
  unit: 8px
  shell: 12px
  panel: 14px
  dense: 6px
  gutter: 12px
  panel-gap: 14px
  chart-min-height: 430px
  summary-row-height: 56px
  sidebar-width: 280px
  inspector-width: 260px
  rail-width: 68px
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.panel}"
  primary-button:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    height: 40px
    padding: 0 14px
  data-table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
  run-context-bar:
    backgroundColor: "{colors.surface-data}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: "{spacing.summary-row-height}"
    padding: 8px 12px
  metric-tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: 78px
    padding: 12px 14px
  chart-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    height: "{spacing.chart-min-height}"
    padding: 0px
  inspector-panel:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    width: "{spacing.inspector-width}"
  control-sidebar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    width: "{spacing.sidebar-width}"
---

## Overview

Institutional Quant Console is a high-density research console rather than a marketing interface. It should feel like a focused quant terminal: compact navigation, quiet panels, precise tables, chart-first analysis, and persistent status surfaces. The screen must support repeated use without visual fatigue.

## Colors

Use deep navy for the persistent platform chrome (`--color-platform-rail`, `--color-platform-nav`, `--color-platform-ink`) and pale gray-blue for the workbench background. White panels carry data. Blue is reserved for primary actions, selection, progress, and equity lines. A-share market semantics are fixed: red means buy/up and green means sell/down.

## Typography

Chinese UI copy uses a CJK system sans stack for reliable rendering. Numeric data must use tabular numerals. Code previews, run IDs, and terminal-like surfaces use the mono stack. Headings stay compact; this product should not use hero-scale type inside operational views.

## Layout

The default desktop layout is a three-pane console: left configuration, center analysis, right job/data/history inspector. The rail and top nav are persistent. Panels should align to an 8px grid, keep 8px radius or below, and favor borders over decorative shadows. Background texture may use subtle gridlines to reinforce the research-console feel.

Backtest results must use a result-focused layout. Once a run exists, the center analysis canvas takes priority over keeping every operational panel visible. The result page starts with a compact run-context-bar, then metric-tile KPI ribbon, then chart-panel surfaces. Config Drawer and Inspector Drawer are auxiliary surfaces, not permanent columns.

Breakpoint rules are explicit: at 1920px and wider, the result workspace may pin an inspector if the main chart remains wide; from 1180px-1919px, only the main result canvas is persistent and side surfaces open as drawers; below 1180px, the result content comes first and auxiliary surfaces remain secondary. The K-line chart is the primary result view and should keep at least 70% of its chart-panel visible in the first desktop viewport.

## Components

Panels, metric tiles, data tables, segmented controls, and pills should be visually related: thin borders, muted headers, compact labels, and clear active states. Tables and charts are first-class surfaces; avoid card nesting and ornamental blocks. Empty states should be brief and operational.

The run-context-bar carries symbol, strategy, range, provider, run id, status, and lightweight actions. Metric-tile is for decision metrics only. Chart-panel is for K-line, volume, equity, and drawdown visuals and must not be squeezed by data catalogs or completed job metadata. Inspector-panel may show job, history, trade, or lineage details only after the user opens the Inspector Drawer.

## Do's and Don'ts

Do keep charts, metrics, and run metadata immediately scannable. Do use red/green only for market meaning. Do keep controls dense but touch-safe on coarse pointers.

Do collapse or demote completed-state side panels once a backtest result exists. Do keep only one persistent auxiliary surface beside the main analysis below 1920px. Do treat readable chart width and first-viewport chart visibility as layout requirements, not nice-to-have polish.

Don't use large hero sections, rounded marketing cards, decorative blobs, one-note gradients, or colorful left-rail accents. Don't hide core analysis behind top-level tabs when the user has already run a backtest. Don't let data catalog, recent runs, simulation placeholders, or completed job metadata compete with active result analysis.
