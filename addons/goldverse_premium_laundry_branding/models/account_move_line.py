from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    goldverse_running_balance = fields.Monetary(
        string="Running Balance",
        compute="_compute_goldverse_running_balance",
        currency_field="company_currency_id",
    )

    @api.depends("date", "balance", "partner_id", "account_id", "company_id", "parent_state")
    def _compute_goldverse_running_balance(self):
        MoveLine = self.env["account.move.line"].sudo()
        for line in self:
            if (
                not line.company_id
                or not line.partner_id
                or not line.account_id
                or line.parent_state != "posted"
            ):
                line.goldverse_running_balance = line.balance
                continue

            commercial_partner = line.partner_id.commercial_partner_id
            account_type = line.account_id.account_type
            domain = [
                ("company_id", "=", line.company_id.id),
                ("partner_id.commercial_partner_id", "=", commercial_partner.id),
                ("account_id.account_type", "=", account_type),
                ("parent_state", "=", "posted"),
                "|",
                ("date", "<", line.date),
                "&",
                ("date", "=", line.date),
                ("id", "<=", line.id),
            ]
            line.goldverse_running_balance = sum(MoveLine.search(domain).mapped("balance"))
