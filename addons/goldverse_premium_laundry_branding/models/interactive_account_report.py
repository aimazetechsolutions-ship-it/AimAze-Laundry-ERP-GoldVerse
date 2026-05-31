from odoo import _, api, fields, models
from odoo.tools.misc import get_lang


class InteractiveAccountReport(models.AbstractModel):
    _inherit = "account.interactive.report"

    @api.model
    def _normalize_options(self, report_key, options=None):
        normalized = super()._normalize_options(report_key, options=options)
        normalized["account_ids"] = [
            int(account_id)
            for account_id in (options or {}).get("account_ids", [])
            if account_id
        ]
        return normalized

    @api.model
    def _general_ledger_report(self, options):
        journals = self._selected_journal_ids(options)
        wizard = self.env["account.report.general.ledger"].create(
            {
                "date_from": options["date_from"],
                "date_to": options["date_to"],
                "target_move": options["target_move"],
                "display_account": options["display_account"],
                "company_id": self.env.company.id,
                "initial_balance": options["initial_balance"],
                "sortby": options["sortby"],
                "journal_ids": [(6, 0, journals)],
            }
        )
        data = {
            "ids": [],
            "model": "ir.ui.menu",
            "form": wizard.read(["date_from", "date_to", "journal_ids", "target_move", "company_id"])[0],
        }
        data["form"].update(wizard.read(["display_account", "initial_balance", "sortby"])[0])
        data["form"]["used_context"] = dict(wizard._build_contexts(data), lang=get_lang(self.env).code)
        account_domain = [("company_ids", "in", [self.env.company.id])]
        if options.get("account_ids"):
            account_domain.append(("id", "in", options["account_ids"]))
        accounts = self.env["account.account"].search(account_domain, order="code")
        account_lines = self.env["report.base_accounting_kit.report_general_ledger"].with_context(
            data["form"]["used_context"]
        )._get_account_move_entry(accounts, options["initial_balance"], options["sortby"], options["display_account"])
        columns = [
            {"key": "name", "label": _(""), "type": "text"},
            {"key": "date", "label": _("Date"), "type": "text"},
            {"key": "partner", "label": _("Partner"), "type": "text"},
            {"key": "currency", "label": _("Currency"), "type": "text"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
            {"key": "balance", "label": _("Balance"), "type": "number"},
        ]
        lines = []
        accounts_by_code = {account.code: account.id for account in accounts}
        line_ids = [
            move.get("lid")
            for account in account_lines
            for move in (account.get("move_lines") or [])
            if move.get("lid")
        ]
        move_by_line_id = {
            line.id: line.move_id.id
            for line in self.env["account.move.line"].browse(line_ids).exists()
            if line.move_id
        }
        for index, account in enumerate(account_lines):
            real_account_id = accounts_by_code.get(account["code"])
            account_id = f"account_{real_account_id or index}"
            lines.append(
                {
                    "id": account_id,
                    "name": f"{account['code']} {account['name']}",
                    "level": 1,
                    "type": "account",
                    "is_total": True,
                    "action": self._move_line_action(
                        _("Journal Items"),
                        options,
                        account_ids=[real_account_id],
                        date_from=False,
                    )
                    if real_account_id
                    else False,
                    "values": {
                        "date": "",
                        "name": f"{account['code']} {account['name']}",
                        "journal": "",
                        "partner": "",
                        "currency": self.env.company.currency_id.name or "",
                        "debit": account.get("debit") or 0.0,
                        "credit": account.get("credit") or 0.0,
                        "balance": account.get("balance") or 0.0,
                    },
                }
            )
            for move_index, move in enumerate(account.get("move_lines") or []):
                move_id = move_by_line_id.get(move.get("lid"))
                move_name = move.get("move_name") or ""
                line_name = move.get("lname") or ""
                if move_name and line_name and line_name not in move_name:
                    entry_name = f"{move_name} {line_name}"
                else:
                    entry_name = line_name or move_name
                lines.append(
                    {
                        "id": f"{account_id}_{move_index}",
                        "name": entry_name,
                        "level": 2,
                        "type": "move",
                        "is_total": False,
                        "move_action": self._journal_entry_action(move_id) if move_id else False,
                        "move_url": f"/odoo/action-274/{move_id}" if move_id else False,
                        "values": {
                            "date": fields.Date.to_string(move.get("ldate")) if move.get("ldate") else "",
                            "name": entry_name,
                            "journal": move.get("lcode") or "",
                            "partner": move.get("partner_name") or "",
                            "currency": self.env.company.currency_id.name or "",
                            "debit": move.get("debit") or 0.0,
                            "credit": move.get("credit") or 0.0,
                            "balance": move.get("balance") or 0.0,
                        },
                    }
                )
        return columns, lines

    @api.model
    def _aged_partner_report(self, options):
        account_types, report_name = self._goldverse_aged_account_types(options)
        date_to = fields.Date.from_string(options["date_to"])
        period_length = max(options["period_length"], 1)
        currency = self.env.company.currency_id
        periods = {
            "4": f"1-{period_length}",
            "3": f"{period_length + 1}-{period_length * 2}",
            "2": f"{period_length * 2 + 1}-{period_length * 3}",
            "1": f"{period_length * 3 + 1}-{period_length * 4}",
            "0": _("Older"),
        }
        columns = [
            {"key": "name", "label": "", "type": "text"},
            {"key": "invoice_date", "label": _("Invoice Date"), "type": "text"},
            {"key": "direction", "label": _("At Date"), "type": "number"},
            {"key": "4", "label": periods["4"], "type": "number"},
            {"key": "3", "label": periods["3"], "type": "number"},
            {"key": "2", "label": periods["2"], "type": "number"},
            {"key": "1", "label": periods["1"], "type": "number"},
            {"key": "0", "label": periods["0"], "type": "number"},
            {"key": "total", "label": _("Total"), "type": "number"},
        ]
        bucket_keys = ("direction", "4", "3", "2", "1", "0", "total")
        totals = {key: 0.0 for key in bucket_keys}
        partners = {}
        move_states = ["posted"] if options["target_move"] == "posted" else ["draft", "posted"]
        domain = [
            ("company_id", "=", self.env.company.id),
            ("parent_state", "in", move_states),
            ("account_id.account_type", "in", account_types),
            ("date", "<=", date_to),
        ]
        move_lines = self.env["account.move.line"].sudo().search(
            domain,
            order="partner_id, date_maturity, date, id",
        )
        for line in move_lines:
            amount = self._goldverse_aged_open_amount(line, date_to, currency)
            if currency.is_zero(amount):
                continue
            partner_id = line.partner_id.id or False
            partner_values = partners.setdefault(
                partner_id,
                {
                    "partner_id": partner_id,
                    "name": line.partner_id.display_name or _("Unknown Partner"),
                    **{key: 0.0 for key in bucket_keys},
                },
            )
            bucket = self._goldverse_aged_bucket(line.date_maturity or line.date, date_to, period_length)
            partner_values[bucket] += amount
            partner_values["total"] += amount
            totals[bucket] += amount
            totals["total"] += amount
        total_values = {
            "name": report_name,
            "invoice_date": "",
            **totals,
        }
        lines = [
            {
                "id": "aged_total",
                "name": report_name,
                "level": 1,
                "type": "aged_summary",
                "is_total": False,
                "values": total_values,
            }
        ]
        sorted_partners = sorted(
            (
                partner_line
                for partner_line in partners.values()
                if not currency.is_zero(partner_line["total"])
            ),
            key=lambda value: (value["name"] or "").casefold(),
        )
        for index, partner_line in enumerate(sorted_partners):
            values = {
                "name": partner_line["name"],
                "invoice_date": "",
            }
            values.update({key: partner_line[key] for key in bucket_keys})
            action = False
            if partner_line["partner_id"]:
                action = {
                    "type": "ir.actions.act_window",
                    "name": partner_line["name"] or _("Partner Entries"),
                    "res_model": "account.move.line",
                    "view_mode": "list,form",
                    "views": [(False, "list"), (False, "form")],
                    "domain": self._move_line_domain(
                        options,
                        account_types=account_types,
                        date_from=False,
                    )
                    + [("partner_id", "=", partner_line["partner_id"])],
                    "context": {
                        "search_default_group_by_move": 1,
                        "default_company_id": self.env.company.id,
                    },
                }
            lines.append(
                {
                    "id": f"aged_{index}",
                    "name": values["name"],
                    "level": 2,
                    "type": "partner",
                    "is_total": False,
                    "action": action,
                    "values": values,
                }
            )
        return columns, lines

    @api.model
    def _goldverse_aged_account_types(self, options):
        if options["result_selection"] == "customer":
            return ["asset_receivable"], _("Aged Receivable")
        if options["result_selection"] == "supplier":
            return ["liability_payable"], _("Aged Payable")
        return ["liability_payable", "asset_receivable"], _("Aged Partner Balance")

    @api.model
    def _goldverse_aged_bucket(self, maturity_date, date_to, period_length):
        if maturity_date >= date_to:
            return "direction"
        days_overdue = (date_to - maturity_date).days
        if days_overdue <= period_length:
            return "4"
        if days_overdue <= period_length * 2:
            return "3"
        if days_overdue <= period_length * 3:
            return "2"
        if days_overdue <= period_length * 4:
            return "1"
        return "0"

    @api.model
    def _goldverse_aged_open_amount(self, line, date_to, currency):
        company_currency = line.company_id.currency_id
        amount = company_currency._convert(line.balance, currency, line.company_id, date_to)
        for partial in line.matched_debit_ids:
            if partial.max_date <= date_to:
                amount -= partial.company_id.currency_id._convert(
                    partial.amount,
                    currency,
                    partial.company_id,
                    date_to,
                )
        for partial in line.matched_credit_ids:
            if partial.max_date <= date_to:
                amount += partial.company_id.currency_id._convert(
                    partial.amount,
                    currency,
                    partial.company_id,
                    date_to,
                )
        return amount

    @api.model
    def _journal_entry_action(self, move_id):
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Voucher"),
            "res_model": "account.move",
            "res_id": move_id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
