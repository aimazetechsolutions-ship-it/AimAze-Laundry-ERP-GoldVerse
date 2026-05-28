from odoo import _, fields, models
from odoo.exceptions import UserError


class LaundryPaymentWizard(models.TransientModel):
    _name = "aimaze.laundry.payment.wizard"
    _description = "Register Laundry Payment"

    order_id = fields.Many2one("aimaze.laundry.order", required=True)
    partner_id = fields.Many2one(related="order_id.partner_id", readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    amount_due = fields.Monetary(related="order_id.balance_amount", currency_field="currency_id", readonly=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    is_advance = fields.Boolean(default=True)
    payment_method_id = fields.Many2one("aimaze.laundry.payment.method")
    journal_id = fields.Many2one("account.journal", required=True)
    payment_date = fields.Date(default=fields.Date.context_today)
    memo = fields.Char()

    def action_register_payment(self):
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("Payment amount must be greater than zero."))
        self.order_id.flush_recordset()
        payment_method_line = self.journal_id.inbound_payment_method_line_ids[:1]
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_id.id,
                "amount": self.amount,
                "currency_id": self.currency_id.id,
                "date": self.payment_date,
                "journal_id": self.journal_id.id,
                "payment_method_line_id": payment_method_line.id if payment_method_line else False,
                "memo": self.memo or self.order_id.name,
                "aimaze_laundry_order_id": self.order_id.id,
                "laundry_is_advance": self.is_advance,
            }
        )
        payment.action_post()
        self.order_id.message_post(body=_("Laundry payment registered: %s %s") % (self.amount, self.currency_id.name))
        if self.order_id.balance_amount <= 0.01:
            self.order_id.write({"state": "paid"})
        return {"type": "ir.actions.act_window_close"}
