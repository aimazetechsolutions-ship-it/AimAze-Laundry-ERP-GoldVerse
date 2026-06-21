"""Book every customer overpayment to a dedicated income account.

Policy: a customer must never carry a negative receivable balance.
Any cash, bank, or IBFT receipt that exceeds the invoice/order amount
is reclassified into account 411099 'Customer Overpayment Income'
via a misc journal entry that fully reconciles the AR credit residual.
"""
from odoo import _, api, fields, models

GOLDVERSE_OVERPAYMENT_CODE = "411099"
GOLDVERSE_OVERPAYMENT_NAME = "Customer Overpayment Income"


class AccountAccount(models.Model):
    _inherit = "account.account"

    goldverse_is_overpayment_income = fields.Boolean(
        string="GoldVerse Overpayment Income",
        default=False,
        index=True,
    )

    @api.model
    def _goldverse_get_overpayment_income_account(self, company=None):
        company = company or self.env.company
        account = self.sudo().search(
            [("goldverse_is_overpayment_income", "=", True), ("company_ids", "in", company.id)],
            limit=1,
        )
        if account:
            return account
        account = self.sudo().search(
            [("code", "=", GOLDVERSE_OVERPAYMENT_CODE), ("company_ids", "in", company.id)],
            limit=1,
        )
        if account:
            account.write({"goldverse_is_overpayment_income": True})
            return account
        return self.sudo().create({
            "code": GOLDVERSE_OVERPAYMENT_CODE,
            "name": GOLDVERSE_OVERPAYMENT_NAME,
            "account_type": "income",
            "company_ids": [(6, 0, [company.id])],
            "goldverse_is_overpayment_income": True,
        })


class AccountMove(models.Model):
    _inherit = "account.move"

    goldverse_is_overpayment_correction = fields.Boolean(
        string="GoldVerse Overpayment Correction",
        default=False,
        index=True,
        copy=False,
    )


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _create_payments(self):
        payments = super()._create_payments()
        for payment in payments:
            payment._goldverse_book_excess_to_income()
        return payments


class AccountPayment(models.Model):
    _inherit = "account.payment"

    goldverse_overpayment_correction_id = fields.Many2one(
        "account.move",
        string="Overpayment Correction Entry",
        readonly=True,
        copy=False,
    )

    def _goldverse_book_excess_to_income(self):
        """If this inbound payment left the partner with a credit AR residual,
        reclassify that residual to the overpayment income account."""
        for payment in self:
            if payment.state not in ("posted", "in_process", "paid"):
                continue
            if payment.payment_type != "inbound":
                continue
            if not payment.partner_id:
                continue
            if payment.goldverse_overpayment_correction_id:
                continue
            partner = payment.partner_id.commercial_partner_id or payment.partner_id
            ar_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
                and not line.full_reconcile_id
                and line.amount_residual < 0
            )
            if not ar_lines:
                continue
            credit_amount = abs(sum(ar_lines.mapped("amount_residual")))
            currency = payment.currency_id or payment.company_id.currency_id
            if currency.is_zero(credit_amount):
                continue
            correction = self.env["account.move"]._goldverse_create_overpayment_correction(
                partner=partner,
                ar_lines=ar_lines,
                amount=credit_amount,
                company=payment.company_id,
                journal=payment.journal_id,
                date=payment.date,
                source_label=payment.name or _("Overpayment"),
            )
            payment.goldverse_overpayment_correction_id = correction.id


class AccountMoveOverpayment(models.Model):
    _inherit = "account.move"

    @api.model
    def _goldverse_create_overpayment_correction(self, partner, ar_lines, amount, company, journal, date, source_label):
        """Create a misc JE: Dr AR, Cr 411099. Reconcile with the prior credit lines."""
        AccountAccount = self.env["account.account"]
        income_account = AccountAccount._goldverse_get_overpayment_income_account(company)
        ar_account = ar_lines.mapped("account_id")[:1]
        if not ar_account:
            return self.browse()
        misc_journal = self.env["account.journal"].sudo().search(
            [("type", "=", "general"), ("company_id", "=", company.id)],
            limit=1,
        )
        if not misc_journal:
            return self.browse()
        currency = ar_lines[:1].currency_id or company.currency_id
        narration = _("GoldVerse overpayment reclassified to income (%s)") % source_label
        move_vals = {
            "journal_id": misc_journal.id,
            "company_id": company.id,
            "date": date,
            "ref": narration,
            "partner_id": partner.id,
            "goldverse_is_overpayment_correction": True,
            "line_ids": [
                (0, 0, {
                    "name": narration,
                    "account_id": ar_account.id,
                    "partner_id": partner.id,
                    "debit": amount,
                    "credit": 0.0,
                    "currency_id": currency.id,
                }),
                (0, 0, {
                    "name": narration,
                    "account_id": income_account.id,
                    "partner_id": partner.id,
                    "debit": 0.0,
                    "credit": amount,
                    "currency_id": currency.id,
                }),
            ],
        }
        move = self.sudo().with_context(
            check_move_validity=False,
            goldverse_skip_lock_check=True,
        ).create(move_vals)
        move.sudo().with_context(goldverse_skip_lock_check=True).action_post()
        # Reconcile the new AR debit line with the original credit lines
        new_ar_line = move.line_ids.filtered(lambda l: l.account_id == ar_account)
        if new_ar_line and ar_lines:
            (new_ar_line + ar_lines).sudo().reconcile()
        return move

    @api.model
    def _goldverse_cleanup_customer_overpayments(self, limit=None):
        """One-shot sweep of every existing AR credit residual.
        Generates per-line misc journal entries dated at the original line's date.
        Idempotent: lines already reconciled (full_reconcile_id set) are skipped.
        """
        MoveLine = self.env["account.move.line"].sudo()
        company = self.env.company
        domain = [
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("amount_residual", "<", 0),
            ("full_reconcile_id", "=", False),
            ("company_id", "=", company.id),
        ]
        ar_lines = MoveLine.search(domain, limit=limit)
        processed = 0
        for ar_line in ar_lines:
            partner = ar_line.partner_id.commercial_partner_id or ar_line.partner_id
            if not partner:
                continue
            currency = ar_line.currency_id or company.currency_id
            credit_amount = abs(ar_line.amount_residual)
            if currency.is_zero(credit_amount):
                continue
            self._goldverse_create_overpayment_correction(
                partner=partner,
                ar_lines=ar_line,
                amount=credit_amount,
                company=company,
                journal=False,
                date=ar_line.date,
                source_label=ar_line.move_id.name or _("Historical credit"),
            )
            processed += 1
        return processed


class LaundryPaymentWizardOverpayment(models.TransientModel):
    _inherit = "aimaze.laundry.payment.wizard"

    def action_register_payment(self):
        result = super().action_register_payment()
        for wizard in self:
            for order in wizard.mapped("order_id"):
                payments = order.payment_ids.filtered(
                    lambda p: p.state in ("posted", "in_process", "paid")
                    and p.payment_type == "inbound"
                    and not p.goldverse_overpayment_correction_id
                )
                payments._goldverse_book_excess_to_income()
        return result
