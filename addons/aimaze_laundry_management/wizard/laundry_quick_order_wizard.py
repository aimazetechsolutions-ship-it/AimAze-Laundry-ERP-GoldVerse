from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LaundryQuickOrderWizard(models.TransientModel):
    _name = "aimaze.laundry.quick.order.wizard"
    _description = "Laundry Quick Counter Order"

    mobile = fields.Char(string="Mobile Number")
    partner_id = fields.Many2one("res.partner", string="Customer")
    customer_name = fields.Char()
    email = fields.Char()
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    company_id = fields.Many2one(related="branch_id.company_id", readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", readonly=True)
    service_category_id = fields.Many2one("aimaze.laundry.service.category")
    service_id = fields.Many2one("aimaze.laundry.service")
    garment_category = fields.Char()
    garment_item = fields.Char()
    quantity = fields.Float(default=1.0)
    unit_price = fields.Monetary(currency_field="currency_id")
    priority = fields.Selection([("normal", "Normal"), ("urgent", "Urgent"), ("express", "Express")], default="normal")
    discount_amount = fields.Monetary(currency_field="currency_id")
    delivery_charge = fields.Monetary(currency_field="currency_id")
    pickup_required = fields.Boolean()
    delivery_required = fields.Boolean()
    advance_amount = fields.Monetary(currency_field="currency_id")
    journal_id = fields.Many2one("account.journal", string="Payment Journal")
    line_ids = fields.One2many("aimaze.laundry.quick.order.wizard.line", "wizard_id")
    wallet_balance = fields.Monetary(compute="_compute_customer_info", currency_field="currency_id")
    loyalty_points = fields.Float(compute="_compute_customer_info")
    previous_balance = fields.Monetary(compute="_compute_customer_info", currency_field="currency_id")
    amount_total = fields.Monetary(compute="_compute_totals", currency_field="currency_id")

    @api.onchange("mobile")
    def _onchange_mobile(self):
        for wizard in self:
            if wizard.mobile and not wizard.partner_id:
                partner = self.env["res.partner"].search([("phone", "=", wizard.mobile)], limit=1)
                if partner:
                    wizard.partner_id = partner
                    wizard.customer_name = partner.name
                    wizard.email = partner.email

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for wizard in self:
            if wizard.partner_id:
                wizard.mobile = wizard.partner_id.phone
                wizard.customer_name = wizard.partner_id.name
                wizard.email = wizard.partner_id.email

    @api.onchange("service_id", "priority", "branch_id", "partner_id")
    def _onchange_service_id(self):
        for wizard in self:
            if wizard.service_id:
                wizard.unit_price = wizard._get_service_price(wizard.service_id)
                if wizard.priority == "urgent":
                    wizard.unit_price *= 1 + (wizard.service_id.urgent_surcharge_percent or 0.0) / 100.0
                elif wizard.priority == "express":
                    wizard.unit_price *= 1 + (wizard.service_id.express_surcharge_percent or 0.0) / 100.0

    @api.depends("partner_id", "currency_id")
    def _compute_customer_info(self):
        MoveLine = self.env["account.move.line"]
        Wallet = self.env["aimaze.customer.wallet"]
        for wizard in self:
            wizard.wallet_balance = 0.0
            wizard.loyalty_points = wizard.partner_id.laundry_loyalty_points if wizard.partner_id else 0.0
            wizard.previous_balance = 0.0
            if wizard.partner_id and wizard.company_id and wizard.currency_id:
                wallet = Wallet.search([("partner_id", "=", wizard.partner_id.id), ("company_id", "=", wizard.company_id.id), ("currency_id", "=", wizard.currency_id.id)], limit=1)
                wizard.wallet_balance = wallet.balance if wallet else 0.0
                domain = [
                    ("partner_id", "=", wizard.partner_id.id),
                    ("company_id", "=", wizard.company_id.id),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                ]
                wizard.previous_balance = sum(MoveLine.search(domain).mapped("amount_residual"))

    @api.depends("line_ids.subtotal", "discount_amount", "delivery_charge")
    def _compute_totals(self):
        for wizard in self:
            wizard.amount_total = max(sum(wizard.line_ids.mapped("subtotal")) + wizard.delivery_charge - wizard.discount_amount, 0.0)

    def _get_service_price(self, service):
        self.ensure_one()
        today = fields.Date.context_today(self)
        RateLine = self.env["aimaze.laundry.rate.card.line"]
        domain = [
            ("service_id", "=", service.id),
            ("rate_card_id.company_id", "=", self.company_id.id),
            "|",
            ("rate_card_id.branch_id", "=", False),
            ("rate_card_id.branch_id", "=", self.branch_id.id),
            "|",
            ("rate_card_id.partner_id", "=", False),
            ("rate_card_id.partner_id", "=", self.partner_id.id if self.partner_id else False),
            "|",
            ("rate_card_id.date_from", "=", False),
            ("rate_card_id.date_from", "<=", today),
            "|",
            ("rate_card_id.date_to", "=", False),
            ("rate_card_id.date_to", ">=", today),
        ]
        line = RateLine.search(domain, order="rate_card_id.partner_id desc, rate_card_id.branch_id desc, price asc", limit=1)
        return line.price if line else service.list_price

    def action_find_customer(self):
        self.ensure_one()
        if not self.mobile:
            raise UserError(_("Enter a mobile number first."))
        partner = self.env["res.partner"].search([("phone", "=", self.mobile)], limit=1)
        if not partner:
            raise UserError(_("No customer found for this mobile number."))
        self.partner_id = partner
        return self._reload()

    def action_create_customer(self):
        self.ensure_one()
        if self.partner_id:
            return self._reload()
        if not self.customer_name:
            raise UserError(_("Enter customer name to create a customer."))
        self.partner_id = self.env["res.partner"].create(
            {
                "name": self.customer_name,
                "phone": self.mobile,
                "email": self.email,
                "customer_rank": 1,
                "laundry_customer_type": "walk_in",
                "laundry_branch_id": self.branch_id.id,
            }
        )
        return self._reload()

    def action_add_service(self):
        self.ensure_one()
        if not self.service_id:
            raise UserError(_("Select a service first."))
        self.write(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "service_id": self.service_id.id,
                            "garment_category": self.garment_category,
                            "garment_item": self.garment_item or self.service_id.name,
                            "quantity": self.quantity,
                            "unit_price": self.unit_price or self._get_service_price(self.service_id),
                            "currency_id": self.currency_id.id,
                        },
                    )
                ]
            }
        )
        return self._reload()

    def action_qty_plus(self):
        self.quantity += 1
        return self._reload()

    def action_qty_minus(self):
        self.quantity = max(self.quantity - 1, 1)
        return self._reload()

    def action_create_order(self):
        self.ensure_one()
        if not self.partner_id:
            self.action_create_customer()
        if not self.line_ids:
            raise UserError(_("Add at least one service line before creating the order."))
        if self.discount_amount and not (self.env.user.has_group("aimaze_laundry_management.group_laundry_admin") or self.env.user.has_group("aimaze_laundry_management.group_branch_manager")):
            raise UserError(_("Only Laundry Admin or Branch Manager can apply manual discounts."))
        order_vals = {
            "partner_id": self.partner_id.id,
            "mobile": self.mobile,
            "customer_type": self.partner_id.laundry_customer_type or "walk_in",
            "branch_id": self.branch_id.id,
            "company_id": self.company_id.id,
            "source": "walk_in",
            "priority": self.priority,
            "pickup_required": self.pickup_required,
            "delivery_required": self.delivery_required,
            "discount_amount": self.discount_amount,
            "delivery_charge": self.delivery_charge,
            "line_ids": [],
        }
        for line in self.line_ids:
            order_vals["line_ids"].append(
                (
                    0,
                    0,
                    {
                        "service_id": line.service_id.id,
                        "garment_category": line.garment_category,
                        "garment_item": line.garment_item,
                        "name": line.service_id.name,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                        "tax_ids": [(6, 0, line.service_id.tax_ids.ids)],
                    },
                )
            )
        order = self.env["aimaze.laundry.order"].create(order_vals)
        order.action_confirm()
        order.flush_recordset()
        if self.advance_amount:
            if not self.journal_id:
                raise UserError(_("Select a payment journal before collecting advance."))
            payment = self.env["account.payment"].create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner_id.id,
                    "amount": self.advance_amount,
                    "currency_id": self.currency_id.id,
                    "date": fields.Date.context_today(self),
                    "journal_id": self.journal_id.id,
                    "payment_method_line_id": self.journal_id.inbound_payment_method_line_ids[:1].id,
                    "memo": _("Counter advance for %s") % order.name,
                    "aimaze_laundry_order_id": order.id,
                    "laundry_is_advance": True,
                }
            )
            payment.action_post()
        return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.order", "res_id": order.id, "view_mode": "form"}

    def _reload(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}


class LaundryQuickOrderWizardLine(models.TransientModel):
    _name = "aimaze.laundry.quick.order.wizard.line"
    _description = "Laundry Quick Counter Order Line"

    wizard_id = fields.Many2one("aimaze.laundry.quick.order.wizard", required=True, ondelete="cascade")
    service_id = fields.Many2one("aimaze.laundry.service", required=True)
    garment_category = fields.Char()
    garment_item = fields.Char()
    quantity = fields.Float(default=1.0)
    unit_price = fields.Monetary(currency_field="currency_id")
    subtotal = fields.Monetary(compute="_compute_subtotal", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency")

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
