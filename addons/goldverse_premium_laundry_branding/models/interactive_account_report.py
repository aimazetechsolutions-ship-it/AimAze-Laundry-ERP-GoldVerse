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
