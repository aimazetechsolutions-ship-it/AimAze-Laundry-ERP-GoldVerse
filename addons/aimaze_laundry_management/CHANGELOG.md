# Changelog

## 19.0.3.0.29 - Ledger Journal Drilldown

- Changed General Ledger line actions so account summary rows drill into journal entries instead of reopening another General Ledger menu.
- Kept actual move-line drilldowns opening the Journal Entry form with the label "View Journal Entry".
- Added a final compact accounting-report styling pass for smaller rows, tighter report paper, visible three-dot controls, and enterprise-style action menus.

## 19.0.3.0.28 - Premium Accounting Reports

- Matched all interactive accounting reports to the requested compact report style with larger export/filter buttons, centered white report paper, and clean table typography.
- Standardized Profit and Loss, Balance Sheet, Trial Balance, General Ledger, and aged report tables with consistent row sizing, totals, zero-value colors, and drill-down icon behavior.
- Kept the Month/Quarter/Year date filter and journal controls aligned with the same professional accounting report toolbar design.

## 19.0.3.0.27 - Modern Accounting Dashboard

- Added a dedicated AimAze-styled accounting journal dashboard theme.
- Converted accounting dashboard journals into a responsive card grid with premium shadows, stage-colored accents, compact buttons, and cleaner graph panels.
- Kept the styling scoped to the standard Accounting dashboard so accounting reports and laundry operations remain unaffected.

## 19.0.3.0.26 - Accounting Date Filter Menu

- Reworked the interactive accounting report date filter to use the professional Month, Quarter, Year, and Custom Dates dropdown style.
- Defaulted accounting reports to a clean monthly period selector when quick periods are hidden.
- Added outside-click closing for accounting report date and journal dropdowns.

## 19.0.3.0.25 - Accounting Report Filter Toolbar

- Standardized the accounting report toolbar across Trial Balance, General Ledger, Profit and Loss, Balance Sheet, and related interactive reports.
- Aligned export buttons, search, date, comparison, journal, posted-entry, and currency filters into a clean single-row desktop layout with responsive wrapping on smaller screens.

## 19.0.3.0.20 - Compact Dashboard Date Popover

- Reduced the executive dashboard custom date popover, input, and footer sizing for mobile screens.
- Loaded dashboard styling in the active Odoo 19 web asset bundle so the compact UI renders reliably.

## 19.0.3.0.19 - Custom Dashboard Date Popover

- Added a professional custom date range pill and popover to the executive dashboard filter area.
- Added outside-click closing and Apply Range behavior so custom dashboard dates refresh cleanly.

## 19.0.3.0.18 - Dashboard Filter Capsule Centering

- Removed the generated Odoo `mb-3` spacing from the executive dashboard period filter option row.
- Forced the inner selection row to center vertically so Today, MTD, YTD, and Custom have equal top and bottom space inside the capsule.

## 19.0.3.0.17 - Segment Text Vertical Alignment

- Strengthened the executive dashboard period filter overrides on the actual generated Odoo field wrapper.
- Centered the segmented filter labels vertically with equal top and bottom spacing inside the capsule.

## 19.0.3.0.16 - Segmented Filter Capsule Fit

- Normalized the dashboard period filter capsule and active badge heights so selected values fit cleanly inside the pill control.
- Removed the external active-badge shadow that made the selected option look detached from the capsule.

## 19.0.3.0.15 - Dashboard Filter Spacing

- Tightened the executive dashboard segmented period filter wrapper so it no longer reserves extra space below the pill row.
- Reduced the dashboard header action gap for a cleaner mobile layout.

## 19.0.3.0.14 - Top-Level Dashboard Menus

- Flattened dashboard menus so Operational, Executive, and Branch dashboards appear directly on the top menu bar.
- Disabled the old nested Operational Dashboard child menu to avoid duplicate entries.

## 19.0.3.0.13 - Dashboard Header Polish

- Moved the executive dashboard period filter to the right side of the dashboard header.
- Added a friendly dashboard display name so Odoo no longer shows the technical transient record name.

## 19.0.3.0.12 - Dashboard Filter Layout

- Hid raw executive dashboard Date From and Date To fields from the top form area.
- Changed the dashboard period filter into a horizontal segmented badge row with inline custom date inputs.

## 19.0.3.0.11 - Menu Label Update

- Renamed the root app-switcher menu entry from AimAze Laundry ERP to Dashboards.

## 19.0.3.0.10 - Segmented Report Filters

- Added AimAze segmented period filters for dashboard/report surfaces: Today, MTD, YTD, and Custom.
- Defaulted the executive dashboard to YTD and added period onchange handling for Today/MTD/YTD/Custom date ranges.

## 19.0.3.0.0 - Phase 5 UI/UX Modernization

- Added AimAze SaaS design system SCSS.
- Added Owl KPI card scaffold for future live dashboard widgets.
- Redesigned executive dashboard with premium KPI shell and alert strips.
- Modernized quick counter order, order kanban, garment kanban, delivery kanban, and complaint kanban.
- Added order, customer, and branch smart buttons.
- Improved driver and garment form layouts with mobile-first workflow hints.
- Modernized portal order, wallet, subscription, pickup, and complaint pages.
- Improved receipt, advance receipt, delivery note, and garment tag report branding.
- Added UI/UX, design, responsive, branding, and performance documentation.
