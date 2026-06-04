from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LaundryAccountConfig(models.Model):
    _inherit = "aimaze.laundry.account.config"

    main_cash_account_id = fields.Many2one(
        "account.account",
        string="Main Cash Account",
    )
    petty_cash_account_id = fields.Many2one(
        "account.account",
        string="Petty Cash Account",
    )
    cash_transfer_journal_id = fields.Many2one(
        "account.journal",
        string="Cash Transfer Journal",
        domain="[('company_id', '=', company_id)]",
    )

    @api.model
    def _goldverse_configure_cash_management(self):
        Account = self.env["account.account"].sudo()
        Journal = self.env["account.journal"].sudo()
        ExpenseHead = self.env["goldverse.cash.expense.head"].sudo()
        expense_types = ("expense", "expense_depreciation", "expense_direct_cost")
        for company in self.env["res.company"].sudo().search([]):
            config = self.sudo().get_config(company) or self.sudo().create({"company_id": company.id})
            main_cash = Account.search([("code", "=", "1126002")], limit=1) or Account.search([("name", "ilike", "Cash Sales")], limit=1)
            petty_cash = Account.search([("code", "=", "1126003")], limit=1) or Account.search([("name", "ilike", "Petty Cash")], limit=1)
            petty_journal = Journal.search([("company_id", "=", company.id), ("name", "ilike", "Petty Cash")], limit=1)
            updates = {}
            if main_cash and not config.main_cash_account_id:
                updates["main_cash_account_id"] = main_cash.id
            if petty_cash and not config.petty_cash_account_id:
                updates["petty_cash_account_id"] = petty_cash.id
            if petty_journal and not config.cash_transfer_journal_id:
                updates["cash_transfer_journal_id"] = petty_journal.id
            if updates:
                config.write(updates)

            expense_accounts = Account.search([("account_type", "in", expense_types)], order="code, name")
            sequence = 10
            for account in expense_accounts:
                if not ExpenseHead.search([("company_id", "=", company.id), ("account_id", "=", account.id)], limit=1):
                    ExpenseHead.create(
                        {
                            "name": "%s %s" % (account.code or "", account.name or account.display_name),
                            "account_id": account.id,
                            "company_id": company.id,
                            "sequence": sequence,
                        }
                    )
                sequence += 10
        return True


class GoldVerseCashExpenseHead(models.Model):
    _name = "goldverse.cash.expense.head"
    _description = "GoldVerse Cash Expense Head"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    account_id = fields.Many2one(
        "account.account",
        required=True,
        tracking=True,
        domain="[('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))]",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_company_unique = models.Constraint("UNIQUE(name, company_id)", "Expense head must be unique per company.")


class GoldVerseCashTransaction(models.Model):
    _name = "goldverse.cash.transaction"
    _description = "GoldVerse Cash Desk Transaction"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, tracking=True)
    transaction_type = fields.Selection(
        [
            ("transfer", "Transfer to Petty Cash"),
            ("expense", "Book Petty Cash Expense"),
        ],
        required=True,
        default="transfer",
        tracking=True,
    )
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one(
        "aimaze.laundry.branch",
        string="Branch",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    user_id = fields.Many2one("res.users", string="Cashier / User", required=True, default=lambda self: self.env.user, tracking=True)
    amount = fields.Monetary(required=True, currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    expense_head_id = fields.Many2one(
        "goldverse.cash.expense.head",
        string="Expense Head",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    description = fields.Char(required=True, tracking=True)
    receipt_attachment = fields.Binary(string="Receipt Attachment")
    receipt_filename = fields.Char()
    account_move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    main_cash_balance = fields.Monetary(compute="_compute_cash_balances", currency_field="currency_id")
    petty_cash_balance = fields.Monetary(compute="_compute_cash_balances", currency_field="currency_id")

    @api.constrains("amount")
    def _check_amount(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_("Amount must be greater than zero."))

    @api.constrains("transaction_type", "expense_head_id")
    def _check_expense_head(self):
        for record in self:
            if record.transaction_type == "expense" and not record.expense_head_id:
                raise ValidationError(_("Expense Head is required for petty cash expenses."))

    @api.depends("company_id")
    def _compute_cash_balances(self):
        MoveLine = self.env["account.move.line"].sudo()
        for record in self:
            config = record._cash_config()
            record.main_cash_balance = record._account_balance(MoveLine, config.main_cash_account_id)
            record.petty_cash_balance = record._account_balance(MoveLine, config.petty_cash_account_id)

    def _account_balance(self, MoveLine, account):
        self.ensure_one()
        if not account:
            return 0.0
        lines = MoveLine.search([
            ("company_id", "=", self.company_id.id),
            ("account_id", "=", account.id),
            ("parent_state", "=", "posted"),
        ])
        return sum(lines.mapped("balance"))

    def _cash_config(self):
        self.ensure_one()
        config = self.env["aimaze.laundry.account.config"].sudo().get_config(self.company_id)
        if not config:
            raise UserError(_("Please create Laundry Accounting Configuration for %s first.") % self.company_id.display_name)
        return config

    def _cash_journal(self, config):
        return config.cash_transfer_journal_id or config.cash_journal_id or self.env["account.journal"].sudo().search(
            [("company_id", "=", self.company_id.id), ("type", "in", ("cash", "general"))],
            limit=1,
        )

    def _cash_accounts(self, config):
        self.ensure_one()
        if not config.main_cash_account_id:
            raise UserError(_("Please set Main Cash Account in Laundry Accounting Configuration."))
        if not config.petty_cash_account_id:
            raise UserError(_("Please set Petty Cash Account in Laundry Accounting Configuration."))
        if self.transaction_type == "transfer":
            return config.petty_cash_account_id, config.main_cash_account_id
        if not self.expense_head_id or not self.expense_head_id.account_id:
            raise UserError(_("Please select an Expense Head with a linked expense account."))
        return self.expense_head_id.account_id, config.petty_cash_account_id

    def _prepare_move_vals(self):
        self.ensure_one()
        config = self._cash_config()
        journal = self._cash_journal(config)
        if not journal:
            raise UserError(_("Please set Cash Transfer Journal or Cash Journal in Laundry Accounting Configuration."))
        debit_account, credit_account = self._cash_accounts(config)
        label = self.description or dict(self._fields["transaction_type"].selection).get(self.transaction_type)
        return {
            "move_type": "entry",
            "date": self.date,
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "ref": self.name if self.name != "New" else label,
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "name": label,
                        "account_id": debit_account.id,
                        "debit": self.amount,
                        "credit": 0.0,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "name": label,
                        "account_id": credit_account.id,
                        "debit": 0.0,
                        "credit": self.amount,
                    },
                ),
            ],
        }

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"].sudo()
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = sequence.next_by_code("goldverse.cash.transaction") or "New"
        return super().create(vals_list)

    def action_post(self):
        for record in self:
            if record.state != "draft":
                continue
            move = self.env["account.move"].sudo().create(record._prepare_move_vals())
            move.action_post()
            record.write({"account_move_id": move.id, "state": "posted"})
        return True

    def action_cancel(self):
        for record in self:
            if record.account_move_id and record.account_move_id.state == "posted":
                raise UserError(_("Posted cash transactions cannot be cancelled here. Reverse the journal entry from Accounting if correction is required."))
            record.state = "cancelled"
        return True

    def action_view_journal_entry(self):
        self.ensure_one()
        if not self.account_move_id:
            raise UserError(_("No journal entry has been posted yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "res_id": self.account_move_id.id,
            "view_mode": "form",
            "target": "current",
        }
