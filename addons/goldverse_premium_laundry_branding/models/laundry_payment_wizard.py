from odoo import api, models


class LaundryPaymentWizard(models.TransientModel):
    _inherit = "aimaze.laundry.payment.wizard"

    def _goldverse_manual_inbound_method(self):
        return self.env["account.payment.method"].search([("code", "=", "manual"), ("payment_type", "=", "inbound")], limit=1)

    def _goldverse_default_payment_journal(self):
        company = self.env.company
        domain = [("type", "in", ("cash", "bank")), ("company_id", "=", company.id)]
        journal = self.env["account.journal"].search(domain + [("inbound_payment_method_line_ids", "!=", False)], limit=1)
        if journal:
            return journal
        return self.env["account.journal"].search(domain, limit=1)

    def _goldverse_ensure_inbound_method_line(self):
        for wizard in self:
            if not wizard.journal_id:
                wizard.journal_id = wizard._goldverse_default_payment_journal()
            if wizard.journal_id and not wizard.journal_id.inbound_payment_method_line_ids:
                method = wizard._goldverse_manual_inbound_method()
                if method:
                    self.env["account.payment.method.line"].create(
                        {
                            "name": method.name,
                            "payment_method_id": method.id,
                            "journal_id": wizard.journal_id.id,
                        }
                    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "journal_id" in fields_list and not values.get("journal_id"):
            journal = self._goldverse_default_payment_journal()
            if journal:
                values["journal_id"] = journal.id
        return values

    @api.onchange("payment_method_id")
    def _onchange_payment_method_id(self):
        for wizard in self:
            if wizard.payment_method_id.journal_id:
                wizard.journal_id = wizard.payment_method_id.journal_id

    def action_register_payment(self):
        self._goldverse_ensure_inbound_method_line()
        return super().action_register_payment()
