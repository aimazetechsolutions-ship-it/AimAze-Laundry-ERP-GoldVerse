import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        try:
            posted._goldverse_reconcile_order_advances()
        except Exception:
            _logger.exception("GoldVerse: failed to auto-reconcile order advances after posting")
        return posted

    def _goldverse_reconcile_order_advances(self):
        Order = self.env["aimaze.laundry.order"].sudo()
        for move in self.filtered(lambda m: m.move_type == "out_invoice" and m.state == "posted"):
            order = Order.search([("invoice_id", "=", move.id)], limit=1)
            if not order:
                continue
            inv_lines = move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
            )
            payments = order.payment_ids.filtered(
                lambda p: p.state in ("posted", "in_process", "paid") and p.payment_type == "inbound"
            )
            pay_lines = payments.mapped("move_id.line_ids").filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
            )
            self._goldverse_reconcile_receivable_lines(inv_lines, pay_lines)

    @api.model
    def _goldverse_reconcile_receivable_lines(self, inv_lines, pay_lines):
        if not inv_lines or not pay_lines:
            return
        by_account = {}
        for line in inv_lines | pay_lines:
            by_account.setdefault(line.account_id.id, self.env["account.move.line"])
            by_account[line.account_id.id] |= line
        for account_lines in by_account.values():
            if len(account_lines) < 2:
                continue
            try:
                account_lines.reconcile()
            except Exception:
                _logger.exception("GoldVerse: reconcile() failed for lines %s", account_lines.ids)

    @api.model
    def _goldverse_backfill_order_advance_reconciliations(self):
        """One-shot pass: reconcile advance payments against already-posted invoices
        for laundry orders that were affected by the legacy non-reconciling flow."""
        Order = self.env["aimaze.laundry.order"].sudo()
        orders = Order.search([
            ("invoice_id", "!=", False),
            ("payment_ids", "!=", False),
        ])
        touched = 0
        for order in orders:
            move = order.invoice_id
            if move.state != "posted":
                continue
            if move.payment_state in ("paid", "reversed"):
                continue
            inv_lines = move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
            )
            payments = order.payment_ids.filtered(
                lambda p: p.state in ("posted", "in_process", "paid") and p.payment_type == "inbound"
            )
            pay_lines = payments.mapped("move_id.line_ids").filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
            )
            if inv_lines and pay_lines:
                self._goldverse_reconcile_receivable_lines(inv_lines, pay_lines)
                touched += 1
        _logger.info("GoldVerse advance backfill: touched %s order(s)", touched)
        return touched

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
