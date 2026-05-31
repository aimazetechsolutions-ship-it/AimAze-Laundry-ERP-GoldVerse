from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _goldverse_uses_invoice_sequence(self):
        self.ensure_one()
        return self.move_type == "out_invoice" and self.journal_id.type == "sale"

    def _goldverse_invoice_sequence_prefix(self):
        self.ensure_one()
        move_date = self.date or self.invoice_date or fields.Date.context_today(self)
        return "GPL/EME/INV/%04d/" % move_date.year

    def _get_starting_sequence(self):
        self.ensure_one()
        if self._goldverse_uses_invoice_sequence():
            return "%s0000" % self._goldverse_invoice_sequence_prefix()
        return super()._get_starting_sequence()

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        self.ensure_one()
        if self._goldverse_uses_invoice_sequence() and with_prefix is None:
            with_prefix = self._goldverse_invoice_sequence_prefix()
        return super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)

    @api.model
    def _goldverse_configure_invoice_sequence(self):
        sale_journals = self.env["account.journal"].sudo().search([
            ("type", "=", "sale"),
            ("company_id", "in", self.env.companies.ids),
        ])
        sale_journals.write({
            "code": "GPL/EME/INV",
            "sequence_override_regex": False,
        })
        return True
