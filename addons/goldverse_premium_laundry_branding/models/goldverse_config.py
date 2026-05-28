from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _goldverse_assign_admin_all_laundry_branches(self):
        admin = self.sudo().search([("login", "=", "admin")], limit=1) or self.env.ref("base.user_admin", raise_if_not_found=False)
        branches = self.env["aimaze.laundry.branch"].sudo().search([])
        if admin and branches:
            admin.write({"laundry_branch_ids": [(6, 0, branches.ids)]})
        return True


class LaundryService(models.Model):
    _inherit = "aimaze.laundry.service"

    goldverse_subcategory_id = fields.Many2one("goldverse.laundry.subcategory", string="Sub Category")
    goldverse_base_price = fields.Monetary(string="Base Price", currency_field="currency_id")
    goldverse_discount_percent = fields.Float(string="Discount (%)")
    goldverse_discount_amount = fields.Monetary(string="Disc (Rs.)", currency_field="currency_id")
    goldverse_net_price = fields.Monetary(string="Net Price", currency_field="currency_id")
    goldverse_search_text = fields.Char(compute="_compute_goldverse_search_text", store=True)

    @api.depends(
        "code",
        "name",
        "category_id.name",
        "goldverse_subcategory_id.name",
        "income_account_id.display_name",
        "pricing_method",
        "goldverse_base_price",
        "goldverse_discount_percent",
        "goldverse_discount_amount",
        "list_price",
        "tax_applicable",
        "active",
    )
    def _compute_goldverse_search_text(self):
        pricing_labels = dict(self._fields["pricing_method"].selection)
        for service in self:
            pricing_method = service.pricing_method or ""
            pricing_label = pricing_labels.get(pricing_method, pricing_method)
            amounts = [
                service.goldverse_base_price,
                service.goldverse_discount_percent,
                service.goldverse_discount_amount,
                service.list_price,
            ]
            amount_text = []
            for amount in amounts:
                amount = amount or 0.0
                amount_text.extend([str(amount), f"{amount:.2f}", f"{amount:,.2f}"])
            service.goldverse_search_text = " ".join(
                filter(
                    None,
                    [
                        service.code,
                        service.name,
                        service.category_id.display_name,
                        service.goldverse_subcategory_id.display_name,
                        service.income_account_id.display_name,
                        pricing_method,
                        pricing_label,
                        " ".join(amount_text),
                        "Tax Applicable" if service.tax_applicable else "Tax Not Applicable",
                        "Active" if service.active else "Inactive",
                    ],
                )
            )

    def _goldverse_prepare_service_values(self, vals):
        return vals

    @api.onchange("goldverse_subcategory_id")
    def _onchange_goldverse_subcategory_id(self):
        return

    @api.onchange("category_id")
    def _onchange_goldverse_category_id(self):
        return

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._goldverse_prepare_service_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._goldverse_prepare_service_values(vals)
        return super().write(vals)


class GoldVerseLaundrySubcategory(models.Model):
    _name = "goldverse.laundry.subcategory"
    _description = "GoldVerse Laundry Sub Category"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    category_id = fields.Many2one("aimaze.laundry.service.category", string="Category")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Sub Category must be unique.")


class GoldVerseLaundryColour(models.Model):
    _name = "goldverse.laundry.colour"
    _description = "GoldVerse Laundry Colour"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class GoldVerseLaundryQcOption(models.Model):
    _name = "goldverse.laundry.qc.option"
    _description = "GoldVerse Laundry QC Option"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    base_qc_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("pass", "Pass"),
            ("fail", "Fail"),
            ("rewash", "Rewash"),
        ],
        default="pending",
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class GoldVerseLaundryTopUp(models.Model):
    _name = "goldverse.laundry.topup"
    _description = "GoldVerse Laundry Add On"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "Add On must be unique.")
