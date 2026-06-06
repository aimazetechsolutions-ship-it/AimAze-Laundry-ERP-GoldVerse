import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    _goldverse_b2b_laundry_types = {"b2b", "corporate", "hotel", "salon", "gym", "restaurant"}

    mobile = fields.Char(string="Mobile")
    goldverse_customer_category = fields.Selection(
        [("b2c", "B2C"), ("b2b", "B2B")],
        string="Customer Type",
        default="b2c",
        required=True,
        tracking=True,
    )
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

    @api.model
    def _goldverse_category_from_laundry_type(self, laundry_customer_type, is_company=False):
        if laundry_customer_type in self._goldverse_b2b_laundry_types or is_company:
            return "b2b"
        return "b2c"

    @api.model
    def _goldverse_prepare_customer_category_vals(self, vals):
        if vals.get("goldverse_customer_category"):
            vals["laundry_customer_type"] = vals["goldverse_customer_category"]
            if vals["goldverse_customer_category"] == "b2b":
                vals.setdefault("is_company", True)
                vals.setdefault("company_type", "company")
            elif vals["goldverse_customer_category"] == "b2c":
                vals.setdefault("is_company", False)
                vals.setdefault("company_type", "person")
            return vals

        if vals.get("laundry_customer_type"):
            vals["goldverse_customer_category"] = self._goldverse_category_from_laundry_type(
                vals["laundry_customer_type"],
                vals.get("is_company", False),
            )
            vals["laundry_customer_type"] = vals["goldverse_customer_category"]
            return vals

        if vals.get("customer_rank", 0) > 0:
            vals.setdefault("goldverse_customer_category", "b2c")
            vals.setdefault("laundry_customer_type", vals["goldverse_customer_category"])
        return vals

    @api.model
    def _goldverse_sync_customer_categories(self):
        partners = self.with_context(active_test=False).sudo().search([])
        for partner in partners:
            category = partner.goldverse_customer_category or self._goldverse_category_from_laundry_type(
                partner.laundry_customer_type,
                partner.is_company,
            )
            vals = {"goldverse_customer_category": category}
            if partner.customer_rank > 0 and partner.laundry_customer_type != category:
                vals["laundry_customer_type"] = category
            partner.write(vals)
        return True

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
            self._goldverse_prepare_customer_category_vals(vals)
        partners = super().create(vals_list)
        partners._goldverse_check_duplicate_mobile()
        return partners

    def write(self, vals):
        vals = dict(vals)
        self._goldverse_prepare_customer_category_vals(vals)
        result = super().write(vals)
        if {"phone", "mobile"} & set(vals):
            self._goldverse_check_duplicate_mobile()
        return result
