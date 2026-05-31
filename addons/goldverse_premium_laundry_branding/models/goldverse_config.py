from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _goldverse_admin_group_xmlids(self):
        return [
            "base.group_system",
            "aimaze_laundry_management.group_laundry_admin",
            "aimaze_laundry_management.group_accountant",
            "account.group_account_invoice",
            "account.group_account_user",
            "account.group_account_manager",
            "base_accounting_kit.group_account_chief",
        ]

    @api.model
    def _goldverse_assign_admin_all_laundry_branches(self):
        admin = self.sudo().search([("login", "=", "admin")], limit=1) or self.env.ref("base.user_admin", raise_if_not_found=False)
        branches = self.env["aimaze.laundry.branch"].sudo().search([])
        if admin and branches:
            admin.write({"laundry_branch_ids": [(6, 0, branches.ids)]})
        return True

    @api.model
    def _goldverse_grant_administrator_full_access(self):
        groups = self.env["res.groups"].sudo()
        for xmlid in self._goldverse_admin_group_xmlids():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                groups |= group.sudo()

        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        if system_group and groups:
            system_group.sudo().write({"implied_ids": [(4, group.id) for group in groups if group != system_group]})

        admin = self.env.ref("base.user_admin", raise_if_not_found=False) or self.sudo().search([("login", "=", "admin")], limit=1)
        if admin and groups:
            admin.sudo().write({"group_ids": [(4, group.id) for group in groups]})

        branches = self.env["aimaze.laundry.branch"].sudo().search([])
        if branches and system_group:
            system_users = system_group.sudo().all_user_ids
            if admin:
                system_users |= admin.sudo()
            system_users.write({"laundry_branch_ids": [(6, 0, branches.ids)]})
        return True


class LaundryService(models.Model):
    _inherit = "aimaze.laundry.service"

    goldverse_subcategory_id = fields.Many2one("goldverse.laundry.subcategory", string="Sub Category")
    goldverse_base_price = fields.Monetary(string="Base Price", currency_field="currency_id")
    goldverse_discount_percent = fields.Float(string="Discount (%)")
    goldverse_discount_amount = fields.Monetary(string="Disc (Rs.)", currency_field="currency_id")
    goldverse_net_price = fields.Monetary(string="Net Price", currency_field="currency_id")
    goldverse_search_text = fields.Char(compute="_compute_goldverse_search_text", store=True)

    @api.onchange("goldverse_base_price", "goldverse_discount_percent")
    def _onchange_goldverse_price_master_percent(self):
        for service in self:
            service._goldverse_sync_price_fields("percent")

    @api.onchange("goldverse_discount_amount")
    def _onchange_goldverse_price_master_amount(self):
        for service in self:
            service._goldverse_sync_price_fields("amount")

    @api.onchange("goldverse_net_price")
    def _onchange_goldverse_price_master_net(self):
        for service in self:
            service._goldverse_sync_price_fields("net")

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

    def _goldverse_compute_price_values(self, values, source="percent"):
        base_price = values.get("goldverse_base_price") or 0.0
        discount_percent = values.get("goldverse_discount_percent") or 0.0
        discount_amount = values.get("goldverse_discount_amount") or 0.0
        net_price = values.get("goldverse_net_price")

        if source == "amount":
            discount_percent = (discount_amount / base_price) * 100.0 if base_price else 0.0
        elif source == "net":
            discount_amount = max(base_price - (net_price or 0.0), 0.0)
            discount_percent = (discount_amount / base_price) * 100.0 if base_price else 0.0
        else:
            discount_amount = base_price * discount_percent / 100.0

        net_price = max(base_price - discount_amount, 0.0)
        return {
            "goldverse_discount_percent": discount_percent,
            "goldverse_discount_amount": discount_amount,
            "goldverse_net_price": net_price,
            "list_price": net_price,
        }

    def _goldverse_price_values_from_record(self):
        self.ensure_one()
        return {
            "goldverse_base_price": self.goldverse_base_price,
            "goldverse_discount_percent": self.goldverse_discount_percent,
            "goldverse_discount_amount": self.goldverse_discount_amount,
            "goldverse_net_price": self.goldverse_net_price,
        }

    def _goldverse_sync_price_fields(self, source="percent"):
        self.ensure_one()
        values = self._goldverse_price_values_from_record()
        computed = self._goldverse_compute_price_values(values, source)
        self.goldverse_discount_percent = computed["goldverse_discount_percent"]
        self.goldverse_discount_amount = computed["goldverse_discount_amount"]
        self.goldverse_net_price = computed["goldverse_net_price"]
        self.list_price = computed["list_price"]

    def _goldverse_prepare_service_values(self, vals):
        price_fields = {
            "goldverse_base_price",
            "goldverse_discount_percent",
            "goldverse_discount_amount",
            "goldverse_net_price",
            "list_price",
        }
        if price_fields & set(vals):
            values = self._goldverse_price_values_from_record() if self else {}
            values.update(vals)
            if "goldverse_net_price" not in vals and "list_price" in vals:
                values["goldverse_net_price"] = vals["list_price"]
            source = "percent"
            if "goldverse_discount_amount" in vals and "goldverse_discount_percent" not in vals:
                source = "amount"
            if {"goldverse_net_price", "list_price"} & set(vals) and not {"goldverse_discount_percent", "goldverse_discount_amount"} & set(vals):
                source = "net"
            vals.update(self._goldverse_compute_price_values(values, source))
        return vals

    def _goldverse_sync_draft_order_lines(self):
        Line = self.env["aimaze.laundry.order.line"].sudo()
        for service in self:
            draft_lines = Line.search([("service_id", "=", service.id), ("order_id.state", "=", "draft")])
            draft_lines.write({"unit_price": service.list_price})
        return True

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
        price_fields = {
            "goldverse_base_price",
            "goldverse_discount_percent",
            "goldverse_discount_amount",
            "goldverse_net_price",
            "list_price",
        }
        if not (price_fields & set(vals)):
            return super().write(vals)
        result = True
        for service in self:
            service_vals = dict(vals)
            service._goldverse_prepare_service_values(service_vals)
            result = super(LaundryService, service).write(service_vals) and result
            service._goldverse_sync_draft_order_lines()
        return result


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
