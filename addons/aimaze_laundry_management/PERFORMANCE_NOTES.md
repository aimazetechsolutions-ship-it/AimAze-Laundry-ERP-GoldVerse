# Phase 5 Performance Notes

Phase 5 keeps the UI fast by using server-rendered Odoo views, CSS enhancements, and lightweight Owl component scaffolding.

## Performance Choices

- No heavy charting library is bundled.
- Dashboard cards use existing computed fields.
- Kanban enhancements are template and CSS based.
- Portal modernization uses QWeb and responsive CSS.
- Report styling is inline/QWeb-friendly for PDF rendering.

For high-volume SaaS tenants, add cached dashboard snapshots and bus-based refresh only where needed.
