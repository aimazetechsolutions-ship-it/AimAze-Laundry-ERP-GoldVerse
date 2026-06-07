from odoo import api, models


class GoldVerseListTotals(models.AbstractModel):
    _inherit = "base"

    @api.model
    def goldverse_list_totals(self, domain=None, fields_to_total=None):
        """Return numeric totals for the active list domain using current user's access."""
        domain = domain or []
        numeric_types = {"float", "integer", "monetary"}
        fields_to_total = [
            field_name
            for field_name in (fields_to_total or [])
            if field_name in self._fields and self._fields[field_name].type in numeric_types
        ]
        if not fields_to_total:
            return {}

        try:
            grouped = self.read_group(domain, fields_to_total, [])
            if grouped:
                return {field_name: grouped[0].get(field_name) or 0.0 for field_name in fields_to_total}
        except Exception:
            # Some computed/reporting models are not friendly to read_group; search preserves access rules.
            records = self.search(domain)
            return {field_name: sum(records.mapped(field_name)) for field_name in fields_to_total}

        return {field_name: 0.0 for field_name in fields_to_total}
