import base64
from datetime import date
from io import BytesIO

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover - Odoo server has xlsxwriter through accounting reports.
    xlsxwriter = None


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
            company_account_domain = [("company_ids", "in", company.id)]
            main_cash = (
                Account.search(company_account_domain + [("code", "=", "216001")], limit=1)
                or Account.search(company_account_domain + [("name", "ilike", "Cash Sales")], limit=1)
            )
            petty_cash = (
                Account.search(company_account_domain + [("code", "=", "216002")], limit=1)
                or Account.search(company_account_domain + [("name", "ilike", "Petty Cash")], limit=1)
            )
            petty_journal = Journal.search([("company_id", "=", company.id), ("name", "ilike", "Petty Cash")], limit=1)
            cash_journal = (
                petty_journal
                or config.cash_journal_id
                or Journal.search([("company_id", "=", company.id), ("type", "=", "cash")], limit=1)
                or Journal.search([("company_id", "=", company.id), ("type", "=", "general")], limit=1)
            )
            updates = {}
            if main_cash and not config.main_cash_account_id:
                updates["main_cash_account_id"] = main_cash.id
            if petty_cash and not config.petty_cash_account_id:
                updates["petty_cash_account_id"] = petty_cash.id
            if cash_journal and not config.cash_transfer_journal_id:
                updates["cash_transfer_journal_id"] = cash_journal.id
            if updates:
                config.write(updates)

            expense_accounts = Account.search(company_account_domain + [("account_type", "in", expense_types)], order="code, name")
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


class GoldVerseCashReportWizard(models.TransientModel):
    _name = "goldverse.cash.report.wizard"
    _description = "GoldVerse Cash Summary Report"

    date_filter = fields.Selection(
        [
            ("today", "Today"),
            ("mtd", "MTD"),
            ("ytd", "YTD"),
            ("custom", "Custom"),
        ],
        default="today",
        required=True,
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one("aimaze.laundry.branch", domain="[('company_id', '=', company_id)]")
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    opening_cash = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_received = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_paid = fields.Monetary(currency_field="currency_id", readonly=True)
    closing_cash = fields.Monetary(currency_field="currency_id", readonly=True)
    line_ids = fields.One2many("goldverse.cash.report.line", "wizard_id", readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        values.setdefault("date_filter", "today")
        values.setdefault("date_from", today)
        values.setdefault("date_to", today)
        return values

    @api.model
    def action_open_report(self):
        wizard = self.create({})
        wizard._apply_date_filter()
        wizard._refresh_report()
        return wizard._action_reload()

    def _action_reload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cash Summary Report"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _apply_date_filter(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.date_filter == "today":
            self.date_from = today
            self.date_to = today
        elif self.date_filter == "mtd":
            self.date_from = date(today.year, today.month, 1)
            self.date_to = today
        elif self.date_filter == "ytd":
            self.date_from = date(today.year, 1, 1)
            self.date_to = today

    def _transaction_domain(self, before_range=False):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
        ]
        if self.branch_id:
            domain.append(("branch_id", "=", self.branch_id.id))
        if before_range:
            domain.append(("date", "<", self.date_from))
        else:
            domain.extend([("date", ">=", self.date_from), ("date", "<=", self.date_to)])
        return domain

    def _refresh_report(self):
        Transaction = self.env["goldverse.cash.transaction"].sudo()
        Line = self.env["goldverse.cash.report.line"].sudo()
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_("Date From cannot be later than Date To."))
            wizard.line_ids.unlink()
            opening_transactions = Transaction.search(wizard._transaction_domain(before_range=True))
            period_transactions = Transaction.search(wizard._transaction_domain(), order="date, id")
            opening = sum(opening_transactions.filtered(lambda rec: rec.transaction_type == "transfer").mapped("amount"))
            opening -= sum(opening_transactions.filtered(lambda rec: rec.transaction_type == "expense").mapped("amount"))
            received = sum(period_transactions.filtered(lambda rec: rec.transaction_type == "transfer").mapped("amount"))
            paid = sum(period_transactions.filtered(lambda rec: rec.transaction_type == "expense").mapped("amount"))
            balance = opening
            line_commands = []
            for transaction in period_transactions:
                received_amount = transaction.amount if transaction.transaction_type == "transfer" else 0.0
                paid_amount = transaction.amount if transaction.transaction_type == "expense" else 0.0
                balance += received_amount - paid_amount
                line_commands.append(
                    (
                        0,
                        0,
                        {
                            "date": transaction.date,
                            "transaction_id": transaction.id,
                            "name": transaction.name,
                            "transaction_type": transaction.transaction_type,
                            "branch_id": transaction.branch_id.id,
                            "user_id": transaction.user_id.id,
                            "expense_head_id": transaction.expense_head_id.id,
                            "description": transaction.description,
                            "cash_received": received_amount,
                            "cash_paid": paid_amount,
                            "balance": balance,
                            "currency_id": wizard.currency_id.id,
                        },
                    )
                )
            wizard.write(
                {
                    "opening_cash": opening,
                    "cash_received": received,
                    "cash_paid": paid,
                    "closing_cash": opening + received - paid,
                    "line_ids": line_commands,
                }
            )

    def action_filter_today(self):
        self.write({"date_filter": "today"})
        self._apply_date_filter()
        self._refresh_report()
        return self._action_reload()

    def action_filter_mtd(self):
        self.write({"date_filter": "mtd"})
        self._apply_date_filter()
        self._refresh_report()
        return self._action_reload()

    def action_filter_ytd(self):
        self.write({"date_filter": "ytd"})
        self._apply_date_filter()
        self._refresh_report()
        return self._action_reload()

    def action_apply_custom(self):
        self.write({"date_filter": "custom"})
        self._refresh_report()
        return self._action_reload()

    def _format_amount(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        return "%s %s" % ("{:,.2f}".format(amount or 0.0), currency.name or "")

    def _period_label(self):
        self.ensure_one()
        return "%s to %s" % (
            fields.Date.to_string(self.date_from),
            fields.Date.to_string(self.date_to),
        )

    def _report_payload(self):
        self.ensure_one()
        self._refresh_report()
        return {
            "company": self.company_id.display_name,
            "branch": self.branch_id.display_name if self.branch_id else _("All Branches"),
            "date_filter": dict(self._fields["date_filter"].selection).get(self.date_filter),
            "date_from": fields.Date.to_string(self.date_from),
            "date_to": fields.Date.to_string(self.date_to),
            "period_label": self._period_label(),
            "currency": (self.currency_id or self.company_id.currency_id).name,
            "opening_cash": self.opening_cash,
            "cash_received": self.cash_received,
            "cash_paid": self.cash_paid,
            "closing_cash": self.closing_cash,
            "opening_cash_text": self._format_amount(self.opening_cash),
            "cash_received_text": self._format_amount(self.cash_received),
            "cash_paid_text": self._format_amount(self.cash_paid),
            "closing_cash_text": self._format_amount(self.closing_cash),
            "lines": [
                {
                    "date": fields.Date.to_string(line.date),
                    "reference": line.name or "",
                    "type": dict(line._fields["transaction_type"].selection).get(line.transaction_type) or "",
                    "branch": line.branch_id.display_name or "",
                    "user": line.user_id.display_name or "",
                    "expense_head": line.expense_head_id.display_name or "",
                    "description": line.description or "",
                    "cash_received": line.cash_received,
                    "cash_paid": line.cash_paid,
                    "balance": line.balance,
                    "cash_received_text": self._format_amount(line.cash_received),
                    "cash_paid_text": self._format_amount(line.cash_paid),
                    "balance_text": self._format_amount(line.balance),
                }
                for line in self.line_ids
            ],
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("goldverse_premium_laundry_branding.action_report_goldverse_cash_summary_pdf").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("XLSX export library is not available on this Odoo server."))
        payload = self._report_payload()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Cash Summary")
        sheet.hide_gridlines(2)

        title_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": "white", "bg_color": "#714B67", "align": "center", "valign": "vcenter"})
        subtitle_fmt = workbook.add_format({"bold": True, "font_size": 10, "font_color": "#10243A", "align": "center"})
        label_fmt = workbook.add_format({"bold": True, "font_color": "#10243A", "bg_color": "#EAF2F6", "border": 1, "border_color": "#D9E2EC"})
        value_fmt = workbook.add_format({"font_color": "#10243A", "border": 1, "border_color": "#D9E2EC"})
        money_fmt = workbook.add_format({"num_format": '#,##0.00 "PKR"', "align": "right", "border": 1, "border_color": "#D9E2EC"})
        money_total_fmt = workbook.add_format({"num_format": '#,##0.00 "PKR"', "bold": True, "align": "right", "bg_color": "#EAF2F6", "border": 1, "border_color": "#D9E2EC"})
        header_fmt = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#10243A", "align": "center", "valign": "vcenter", "border": 1, "border_color": "#10243A", "text_wrap": True})
        text_fmt = workbook.add_format({"border": 1, "border_color": "#D9E2EC", "valign": "top", "text_wrap": True})
        date_fmt = workbook.add_format({"num_format": "yyyy-mm-dd", "border": 1, "border_color": "#D9E2EC", "align": "center"})
        total_label_fmt = workbook.add_format({"bold": True, "font_color": "#10243A", "bg_color": "#D9E2EC", "border": 1, "border_color": "#C9D3DD"})

        sheet.set_column("A:A", 12)
        sheet.set_column("B:B", 16)
        sheet.set_column("C:C", 15)
        sheet.set_column("D:D", 16)
        sheet.set_column("E:E", 18)
        sheet.set_column("F:F", 24)
        sheet.set_column("G:I", 15)
        sheet.merge_range("A1:I1", "GoldVerse Cash Summary Report", title_fmt)
        sheet.merge_range("A2:I2", "%s | %s | %s" % (payload["company"], payload["branch"], payload["period_label"]), subtitle_fmt)

        summary_rows = [
            ("Opening Cash", payload["opening_cash"]),
            ("Cash Received", payload["cash_received"]),
            ("Cash Paid", payload["cash_paid"]),
            ("Closing Cash in Hand", payload["closing_cash"]),
        ]
        row = 3
        for label, amount in summary_rows:
            sheet.write(row, 0, label, label_fmt)
            sheet.write_number(row, 1, amount or 0.0, money_total_fmt if label == "Closing Cash in Hand" else money_fmt)
            row += 1

        row += 1
        headers = ["Date", "Reference", "Type", "Branch", "User", "Description", "Cash Received", "Cash Paid", "Closing Cash"]
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_fmt)
        row += 1
        for line in payload["lines"]:
            sheet.write(row, 0, line["date"], date_fmt)
            sheet.write(row, 1, line["reference"], text_fmt)
            sheet.write(row, 2, line["type"], text_fmt)
            sheet.write(row, 3, line["branch"], text_fmt)
            sheet.write(row, 4, line["user"], text_fmt)
            sheet.write(row, 5, line["description"], text_fmt)
            sheet.write_number(row, 6, line["cash_received"] or 0.0, money_fmt)
            sheet.write_number(row, 7, line["cash_paid"] or 0.0, money_fmt)
            sheet.write_number(row, 8, line["balance"] or 0.0, money_fmt)
            row += 1

        sheet.merge_range(row, 0, row, 5, "Report Total", total_label_fmt)
        sheet.write_number(row, 6, payload["cash_received"] or 0.0, money_total_fmt)
        sheet.write_number(row, 7, payload["cash_paid"] or 0.0, money_total_fmt)
        sheet.write_number(row, 8, payload["closing_cash"] or 0.0, money_total_fmt)
        sheet.freeze_panes(9, 0)
        workbook.close()
        output.seek(0)

        filename = "GoldVerse Cash Summary %s to %s.xlsx" % (payload["date_from"], payload["date_to"])
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }


class GoldVerseCashReportLine(models.TransientModel):
    _name = "goldverse.cash.report.line"
    _description = "GoldVerse Cash Summary Report Line"
    _order = "date, id"

    wizard_id = fields.Many2one("goldverse.cash.report.wizard", required=True, ondelete="cascade")
    date = fields.Date(readonly=True)
    transaction_id = fields.Many2one("goldverse.cash.transaction", readonly=True)
    name = fields.Char(readonly=True)
    transaction_type = fields.Selection(
        [
            ("transfer", "Cash Received"),
            ("expense", "Cash Paid"),
        ],
        readonly=True,
    )
    branch_id = fields.Many2one("aimaze.laundry.branch", readonly=True)
    user_id = fields.Many2one("res.users", readonly=True)
    expense_head_id = fields.Many2one("goldverse.cash.expense.head", readonly=True)
    description = fields.Char(readonly=True)
    cash_received = fields.Monetary(currency_field="currency_id", readonly=True)
    cash_paid = fields.Monetary(currency_field="currency_id", readonly=True)
    balance = fields.Monetary(string="Closing Cash in Hand", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
