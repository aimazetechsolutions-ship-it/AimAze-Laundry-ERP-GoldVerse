from odoo import api, fields, models


class LaundryPaymentMethod(models.Model):
    _inherit = "aimaze.laundry.payment.method"

    @api.model
    def _goldverse_sync_laundry_payment_methods(self):
        Journal = self.env["account.journal"].sudo()
        company = self.env.company

        cash_journal = Journal.search([("company_id", "=", company.id), ("name", "=", "Cash"), ("type", "=", "cash")], limit=1)
        if not cash_journal:
            cash_journal = Journal.search(
                [
                    ("company_id", "=", company.id),
                    ("type", "=", "cash"),
                    "|",
                    ("name", "=", "Cash Sales"),
                    ("code", "ilike", "CV"),
                ],
                limit=1,
            )
            if cash_journal:
                cash_journal.name = "Cash"

        ibft_journal = Journal.search([("company_id", "=", company.id), ("name", "=", "IBFT"), ("type", "=", "bank")], limit=1)
        if not ibft_journal:
            ibft_journal = Journal.search(
                [
                    ("company_id", "=", company.id),
                    ("type", "=", "bank"),
                    ("name", "not ilike", "POS"),
                ],
                limit=1,
            )
            if ibft_journal:
                ibft_journal.name = "IBFT"

        cash = self.search([("name", "=", "Cash")], limit=1)
        if not cash:
            cash = self.create({"name": "Cash", "method_type": "cash", "sequence": 10})
        cash.write({"name": "Cash", "method_type": "cash", "sequence": 10, "active": True, "journal_id": cash_journal.id if cash_journal else False})

        ibft_methods = self.search([("name", "ilike", "IBFT")], order="sequence, id")
        ibft = ibft_methods[:1]
        if not ibft:
            ibft = self.create({"name": "IBFT", "method_type": "online", "sequence": 20})
        ibft.write({"name": "IBFT", "method_type": "online", "sequence": 20, "active": True, "journal_id": ibft_journal.id if ibft_journal else False})
        (ibft_methods - ibft).write({"active": False})
        return True


class LaundryPaymentWizard(models.TransientModel):
    _inherit = "aimaze.laundry.payment.wizard"

    goldverse_deliver_after_payment = fields.Boolean(default=lambda self: self.env.context.get("default_goldverse_deliver_after_payment"))
    payment_date = fields.Date(default=False)

    def _goldverse_manual_inbound_method(self):
        return self.env["account.payment.method"].search([("code", "=", "manual"), ("payment_type", "=", "inbound")], limit=1)

    def _goldverse_default_payment_journal(self):
        company = self.env.company
        domain = [("type", "in", ("cash", "bank")), ("company_id", "=", company.id), ("name", "in", ["Cash", "IBFT"])]
        cash_domain = [("type", "=", "cash"), ("company_id", "=", company.id), ("name", "=", "Cash")]
        return (
            self.env["account.journal"].search(cash_domain + [("inbound_payment_method_line_ids", "!=", False)], limit=1)
            or self.env["account.journal"].search(cash_domain, limit=1)
            or self.env["account.journal"].search(domain + [("inbound_payment_method_line_ids", "!=", False)], limit=1)
            or self.env["account.journal"].search(domain, limit=1)
        )

    def _goldverse_default_payment_method(self):
        return self.env["aimaze.laundry.payment.method"].search([("active", "=", True), ("name", "=", "Cash")], limit=1)

    def _goldverse_ensure_inbound_method_line(self):
        for wizard in self:
            if not wizard.journal_id:
                wizard.journal_id = wizard._goldverse_default_payment_journal()
            if wizard.journal_id and not wizard.journal_id.inbound_payment_method_line_ids:
                method = wizard._goldverse_manual_inbound_method()
                if method:
                    self.env["account.payment.method.line"].sudo().create(
                        {
                            "name": method.name,
                            "payment_method_id": method.id,
                            "journal_id": wizard.journal_id.id,
                        }
                    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        # User requested: amount, payment method, and payment date should start blank
        # so the cashier explicitly enters each. Journal auto-fills from the payment method.
        values.pop("amount", None)
        values.pop("payment_method_id", None)
        values.pop("payment_date", None)
        values.pop("journal_id", None)
        return values

    @api.onchange("payment_method_id")
    def _onchange_payment_method_id(self):
        for wizard in self:
            if wizard.payment_method_id.journal_id:
                wizard.journal_id = wizard.payment_method_id.journal_id

    def action_register_payment(self):
        for wizard in self:
            if not wizard.payment_date:
                wizard.payment_date = fields.Date.context_today(wizard)
            if not wizard.journal_id and wizard.payment_method_id and wizard.payment_method_id.journal_id:
                wizard.journal_id = wizard.payment_method_id.journal_id
        deliver_after_payment = any(self.mapped("goldverse_deliver_after_payment"))
        orders = self.mapped("order_id")
        previous_states = {order.id: order.state for order in orders}
        self._goldverse_ensure_inbound_method_line()
        result = super(LaundryPaymentWizard, self.sudo()).action_register_payment()
        orders._goldverse_reconcile_order_invoice_payments()
        if not deliver_after_payment:
            for order in orders:
                previous_state = previous_states.get(order.id)
                if previous_state and previous_state not in ("draft", "cancelled", "delivered", "paid"):
                    order.with_context(goldverse_allow_locked_order_write=True, goldverse_skip_required_validation=True).write({"state": previous_state})
        if deliver_after_payment:
            for order in orders:
                order.invalidate_recordset(["balance_amount", "payment_status", "state"])
                if order.balance_amount <= 0.01:
                    order.with_context(goldverse_force_mark_delivered=True).action_mark_delivered()
            return {"type": "ir.actions.client", "tag": "reload"}
        return result
