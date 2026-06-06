import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    mobile = fields.Char(string="Mobile")
    laundry_customer_type = fields.Selection(
        selection_add=[
            ("b2c", "B2C"),
            ("b2b", "B2B"),
        ],
        ondelete={
            "b2c": "set null",
            "b2b": "set null",
        },
    )

    def _goldverse_normalize_mobile(self, value):
        return re.sub(r"\D+", "", value or "")

    def _goldverse_mobile_value(self):
        self.ensure_one()
        return self._goldverse_normalize_mobile(self.mobile or self.phone)

    def _goldverse_check_duplicate_mobile(self):
        all_partners = self.with_context(active_test=False).sudo().search([("id", "not in", self.ids)])
        seen = {}
        for existing in all_partners:
            mobile = existing._goldverse_mobile_value()
            if mobile:
                seen[mobile] = existing
        for partner in self:
            mobile = partner._goldverse_mobile_value()
            if not mobile:
                continue
            duplicate = seen.get(mobile)
            if duplicate:
                raise ValidationError(
                    _("Mobile number %s is already used by customer %s.")
                    % (partner.mobile or partner.phone, duplicate.display_name)
                )
            seen[mobile] = partner

    @api.model_create_multi
    def create(self, vals_list):
        default_customer_rank = self.env.context.get("default_customer_rank")
        default_laundry_customer_type = self.env.context.get("default_laundry_customer_type")
        for vals in vals_list:
            if default_customer_rank and not vals.get("customer_rank"):
                vals["customer_rank"] = default_customer_rank
            if default_laundry_customer_type and not vals.get("laundry_customer_type"):
                vals["laundry_customer_type"] = default_laundry_customer_type
        partners = super().create(vals_list)
        partners._goldverse_check_duplicate_mobile()
        return partners

    def write(self, vals):
        result = super().write(vals)
        if {"phone", "mobile"} & set(vals):
            self._goldverse_check_duplicate_mobile()
        return result
