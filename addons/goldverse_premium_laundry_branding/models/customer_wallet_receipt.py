from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class GoldVerseCustomerWalletReceipt(models.Model):
    _name = "goldverse.customer.wallet.receipt"
    _description = "GoldVerse Customer Wallet Receipt"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "receipt_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Customer", tracking=True)
    mobile = fields.Char(string="Mobile", required=True, tracking=True)
    receipt_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one(
        "aimaze.laundry.branch",
        string="Branch",
        domain="[('company_id', '=', company_id)]",
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one("res.users", string="Cashier / User", required=True, default=lambda self: self.env.user, tracking=True)
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        tracking=True,
    )
    memo = fields.Char(default="Customer wallet advance receipt", tracking=True)
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True, copy=False)
    payment_move_id = fields.Many2one("account.move", string="Journal Entry", related="payment_id.move_id", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        tracking=True,
    )
    ar_credit_balance = fields.Monetary(
        string="Customer AR Credit Balance",
        compute="_compute_ar_credit_balance",
        currency_field="currency_id",
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"].sudo()
        for vals in vals_list:
            self._goldverse_prepare_customer_from_mobile_vals(vals)
            self._goldverse_check_required_receipt_vals(vals)
            if vals.get("name", "New") == "New":
                vals["name"] = sequence.next_by_code("goldverse.customer.wallet.receipt") or "New"
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if "mobile" in vals or "partner_id" in vals:
            self._goldverse_prepare_customer_from_mobile_vals(vals)
        return super().write(vals)

    @api.constrains("amount")
    def _check_amount(self):
        for receipt in self:
            if receipt.amount <= 0:
                raise ValidationError(_("Amount must be greater than zero."))

    @api.constrains("mobile", "branch_id", "journal_id")
    def _check_required_receipt_fields(self):
        for receipt in self:
            missing = []
            if not receipt.mobile:
                missing.append(_("Mobile"))
            if not receipt.branch_id:
                missing.append(_("Branch"))
            if not receipt.journal_id:
                missing.append(_("Journal"))
            if missing:
                raise ValidationError(_("Please fill mandatory fields: %s.") % ", ".join(missing))
            receipt.env["res.partner"]._goldverse_validate_mobile_digits(receipt.mobile)

    @api.model
    def _goldverse_check_required_receipt_vals(self, vals):
        missing = []
        if not vals.get("mobile"):
            missing.append(_("Mobile"))
        if not vals.get("branch_id"):
            missing.append(_("Branch"))
        if not vals.get("journal_id"):
            missing.append(_("Journal"))
        if missing:
            raise ValidationError(_("Please fill mandatory fields: %s.") % ", ".join(missing))
        self.env["res.partner"]._goldverse_validate_mobile_digits(vals.get("mobile"))

    @api.model
    def _goldverse_normalize_mobile(self, value):
        return self.env["res.partner"]._goldverse_normalize_mobile(value)

    @api.model
    def _goldverse_find_customer_by_mobile(self, mobile):
        normalized_mobile = self._goldverse_normalize_mobile(mobile)
        if not normalized_mobile:
            return self.env["res.partner"]
        candidates = self.env["res.partner"].sudo().search([
            ("active", "=", True),
            ("customer_rank", ">", 0),
        ])
        return candidates.filtered(lambda partner: partner._goldverse_mobile_value() == normalized_mobile)[:1]

    @api.model
    def _goldverse_prepare_customer_from_mobile_vals(self, vals):
        partner = self.env["res.partner"].sudo().browse(vals.get("partner_id")) if vals.get("partner_id") else False
        mobile = vals.get("mobile")
        if partner and not mobile:
            vals["mobile"] = self.env["res.partner"]._goldverse_clean_mobile_number(partner.mobile or partner.phone)
            return vals
        if mobile:
            vals["mobile"] = self.env["res.partner"]._goldverse_clean_mobile_number(mobile)
        if vals.get("mobile") and not partner:
            matched_partner = self._goldverse_find_customer_by_mobile(vals["mobile"])
            if matched_partner:
                vals["partner_id"] = matched_partner.id
        return vals

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for receipt in self:
            if not receipt.partner_id:
                continue
            receipt.mobile = self.env["res.partner"]._goldverse_clean_mobile_number(receipt.partner_id.mobile or receipt.partner_id.phone)
            if receipt.partner_id.laundry_branch_id and not receipt.branch_id:
                receipt.branch_id = receipt.partner_id.laundry_branch_id

    @api.onchange("mobile")
    def _onchange_mobile(self):
        for receipt in self:
            if not receipt.mobile:
                receipt.partner_id = False
                continue
            receipt.mobile = self.env["res.partner"]._goldverse_clean_mobile_number(receipt.mobile)
            partner = receipt._goldverse_find_customer_by_mobile(receipt.mobile)
            if partner:
                receipt.partner_id = partner
                if partner.laundry_branch_id and not receipt.branch_id:
                    receipt.branch_id = partner.laundry_branch_id
                continue
            receipt.partner_id = False
            return {
                "warning": {
                    "title": _("Customer Not Found"),
                    "message": _("No customer was found for this mobile number. Create the customer first, then select/post the wallet receipt."),
                }
            }

    @api.model
    def _goldverse_default_receipt_journal(self, company=False):
        company = company or self.env.company
        config = self.env["aimaze.laundry.account.config"].sudo().get_config(company)
        return (
            (config.cash_journal_id if config else False)
            or (config.bank_journal_id if config else False)
            or self.env["account.journal"].sudo().search(
                [("type", "in", ("cash", "bank")), ("company_id", "=", company.id)],
                limit=1,
            )
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "journal_id" in fields_list and not values.get("journal_id"):
            journal = self._goldverse_default_receipt_journal()
            if journal:
                values["journal_id"] = journal.id
        return values

    def _ensure_inbound_method_line(self):
        method = self.env["account.payment.method"].sudo().search(
            [("code", "=", "manual"), ("payment_type", "=", "inbound")],
            limit=1,
        )
        for receipt in self:
            if receipt.journal_id.inbound_payment_method_line_ids:
                continue
            if not method:
                continue
            self.env["account.payment.method.line"].sudo().create(
                {
                    "name": method.name,
                    "payment_method_id": method.id,
                    "journal_id": receipt.journal_id.id,
                }
            )

    def _payment_vals(self):
        self.ensure_one()
        if not self.partner_id and self.mobile:
            partner = self._goldverse_find_customer_by_mobile(self.mobile)
            if partner:
                self.partner_id = partner
        if not self.partner_id:
            raise UserError(_("No customer exists for mobile %s. Create the customer first.") % (self.mobile or ""))
        method_line = self.journal_id.inbound_payment_method_line_ids[:1]
        return {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner_id.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "date": self.receipt_date,
            "journal_id": self.journal_id.id,
            "payment_method_line_id": method_line.id if method_line else False,
            "memo": self.memo or self.name,
            "payment_reference": self.name,
            "goldverse_wallet_receipt_id": self.id,
        }

    def action_post(self):
        for receipt in self:
            if receipt.state != "draft":
                continue
            if not receipt.partner_id and receipt.mobile:
                partner = receipt._goldverse_find_customer_by_mobile(receipt.mobile)
                if partner:
                    receipt.partner_id = partner
            if not receipt.partner_id:
                return receipt.action_create_customer_from_mobile()
            receipt._ensure_inbound_method_line()
            payment = self.env["account.payment"].sudo().create(receipt._payment_vals())
            payment.action_post()
            receipt.write({"payment_id": payment.id, "state": "posted"})
            receipt.message_post(
                body=_("Customer wallet advance received: %(amount).2f %(currency)s. Posted as AR credit payment %(payment)s.")
                % {
                    "amount": receipt.amount,
                    "currency": receipt.currency_id.name,
                    "payment": payment.name or payment.display_name,
                }
            )
        return True

    def action_create_customer_from_mobile(self):
        self.ensure_one()
        if not self.mobile:
            raise UserError(_("Enter mobile before creating a customer."))
        context = {
            "default_customer_rank": 1,
            "default_laundry_customer_type": "b2c",
            "default_goldverse_customer_category": "b2c",
            "default_company_type": "person",
            "default_is_company": False,
            "default_phone": self.mobile,
            "default_mobile": self.mobile,
        }
        if self.branch_id:
            context["default_laundry_branch_id"] = self.branch_id.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Customer"),
            "res_model": "res.partner",
            "view_mode": "form",
            "target": "new",
            "context": context,
        }

    def action_cancel(self):
        for receipt in self:
            if receipt.payment_id and receipt.payment_id.state == "posted":
                raise UserError(_("Posted wallet receipts cannot be reset. Reverse the payment from Accounting if correction is required."))
            receipt.state = "cancelled"
        return True

    def action_view_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment has been posted yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Wallet Receipt Payment"),
            "res_model": "account.payment",
            "res_id": self.payment_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_journal_entry(self):
        self.ensure_one()
        if not self.payment_move_id:
            raise UserError(_("No journal entry has been posted yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "res_id": self.payment_move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends("partner_id", "company_id")
    def _compute_ar_credit_balance(self):
        MoveLine = self.env["account.move.line"].sudo()
        for receipt in self:
            if not receipt.partner_id:
                receipt.ar_credit_balance = 0.0
                continue
            lines = MoveLine.search(receipt._ar_credit_domain())
            receipt.ar_credit_balance = abs(sum(lines.mapped("amount_residual")))

    def _ar_credit_domain(self):
        self.ensure_one()
        commercial = self.partner_id.commercial_partner_id
        return [
            ("company_id", "=", self.company_id.id),
            ("partner_id.commercial_partner_id", "=", commercial.id),
            ("account_id.account_type", "=", "asset_receivable"),
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("amount_residual", "<", 0),
        ]


class AccountPayment(models.Model):
    _inherit = "account.payment"

    goldverse_wallet_receipt_id = fields.Many2one("goldverse.customer.wallet.receipt", string="GoldVerse Wallet Receipt")
