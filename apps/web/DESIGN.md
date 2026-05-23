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
---

## Overview

Institutional Quant Console is a high-density research console rather than a marketing interface. It should feel like a focused quant terminal: compact navigation, quiet panels, precise tables, chart-first analysis, and persistent status surfaces. The screen must support repeated use without visual fatigue.

## Colors

Use deep navy for the persistent platform chrome (`--color-platform-rail`, `--color-platform-nav`, `--color-platform-ink`) and pale gray-blue for the workbench background. White panels carry data. Blue is reserved for primary actions, selection, progress, and equity lines. A-share market semantics are fixed: red means buy/up and green means sell/down.

## Typography

Chinese UI copy uses a CJK system sans stack for reliable rendering. Numeric data must use tabular numerals. Code previews, run IDs, and terminal-like surfaces use the mono stack. Headings stay compact; this product should not use hero-scale type inside operational views.

## Layout

The default desktop layout is a three-pane console: left configuration, center analysis, right job/data/history inspector. The rail and top nav are persistent. Panels should align to an 8px grid, keep 8px radius or below, and favor borders over decorative shadows. Background texture may use subtle gridlines to reinforce the research-console feel.

## Components

Panels, metric tiles, data tables, segmented controls, and pills should be visually related: thin borders, muted headers, compact labels, and clear active states. Tables and charts are first-class surfaces; avoid card nesting and ornamental blocks. Empty states should be brief and operational.

## Do's and Don'ts

Do keep charts, metrics, and run metadata immediately scannable. Do use red/green only for market meaning. Do keep controls dense but touch-safe on coarse pointers.

Don't use large hero sections, rounded marketing cards, decorative blobs, one-note gradients, or colorful left-rail accents. Don't hide core analysis behind top-level tabs when the user has already run a backtest.
