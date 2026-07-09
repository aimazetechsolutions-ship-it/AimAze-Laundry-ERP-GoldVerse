# -*- coding: utf-8 -*-
import calendar
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.tools.misc import get_lang


class InteractiveAccountReport(models.AbstractModel):
    _name = "account.interactive.report"
    _description = "Interactive Accounting Report"

    FINANCIAL_REPORTS = {
        "profit_and_loss": {
            "title": "Profit and Loss",
            "xmlid": "base_accounting_kit.account_financial_report_profitandloss0",
        },
        "balance_sheet": {
            "title": "Balance Sheet",
            "xmlid": "base_accounting_kit.account_financial_report_balancesheet0",
        },
        "cash_flow": {
            "title": "Cash Flow Statement",
            "xmlid": "base_accounting_kit.account_financial_report_cash_flow0",
            "cash_flow": True,
        },
    }

    DIRECT_REPORTS = {
        **FINANCIAL_REPORTS,
        "trial_balance": {"title": "Trial Balance", "kind": "trial_balance"},
        "general_ledger": {"title": "General Ledger", "kind": "general_ledger"},
        "partner_ledger": {"title": "Partner Ledger", "kind": "partner_ledger"},
        "tax_report": {"title": "Tax Report", "kind": "tax_report"},
        "aged_partner_balance": {"title": "Aged Partner Balance", "kind": "aged_partner_balance"},
        "aged_receivable": {
            "title": "Aged Receivable",
            "kind": "aged_partner_balance",
            "result_selection": "customer",
        },
        "aged_payable": {
            "title": "Aged Payable",
            "kind": "aged_partner_balance",
            "result_selection": "supplier",
        },
        "journal_audit": {"title": "Journals Audit", "kind": "journal_audit"},
        "bank_book": {"title": "Bank Book", "kind": "daily_book", "journal_type": "bank"},
        "cash_book": {"title": "Cash Book", "kind": "daily_book", "journal_type": "cash"},
        "day_book": {"title": "Day Book", "kind": "daily_book"},
    }

    @api.model
    def _default_dates(self):
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = fields.Date.from_string(today)
        return date(today.year, 1, 1), today

    @api.model
    def _normalize_options(self, report_key, options=None):
        options = dict(options or {})
        default_from, default_to = self._default_dates()
        if report_key == "trial_balance" and not options.get("date_from"):
            default_from = date(default_to.year, default_to.month, 1)
        target_move = options.get("target_move") if options.get("target_move") in ("posted", "all") else "posted"
        display_account = options.get("display_account") if options.get("display_account") in ("all", "movement", "not_zero") else "movement"
        result_selection = options.get("result_selection") if options.get("result_selection") in ("customer", "supplier", "customer_supplier") else "customer_supplier"
        fixed_result_selection = self.DIRECT_REPORTS.get(report_key, {}).get("result_selection")
        if fixed_result_selection:
            result_selection = fixed_result_selection
        journal_ids = [int(journal_id) for journal_id in options.get("journal_ids", []) if journal_id]
        account_ids = [int(account_id) for account_id in options.get("account_ids", []) if account_id]
        comparison = options.get("comparison")
        if comparison not in ("none", "previous_period", "same_last_year", "custom"):
            comparison = "none"
        # Comparison only applies to Balance Sheet / P&L in GoldVerse — Trial Balance
        # here uses a fixed column layout that does not accept period columns yet.
        if report_key not in ("balance_sheet", "profit_and_loss"):
            comparison = "none"
        try:
            comparison_count = int(options.get("comparison_count") or 1)
        except (TypeError, ValueError):
            comparison_count = 1
        comparison_count = max(1, min(comparison_count, 36))
        cmp_from_str = options.get("comparison_date_from") or ""
        cmp_to_str = options.get("comparison_date_to") or ""
        comparison_label = self._comparison_button_label(comparison, comparison_count, cmp_from_str, cmp_to_str)
        period_order = options.get("period_order") if options.get("period_order") in ("descending", "ascending") else "descending"
        return {
            "date_from": options.get("date_from") or fields.Date.to_string(default_from),
            "date_to": options.get("date_to") or fields.Date.to_string(default_to),
            "comparison": comparison,
            "comparison_count": comparison_count,
            "comparison_date_from": cmp_from_str,
            "comparison_date_to": cmp_to_str,
            "comparison_label": comparison_label,
            "period_order": period_order,
            "target_move": target_move,
            "debit_credit": bool(options.get("debit_credit")),
            "enable_filter": bool(options.get("enable_filter")),
            "display_account": display_account,
            "result_selection": result_selection,
            "initial_balance": bool(options.get("initial_balance")),
            "sortby": options.get("sortby") if options.get("sortby") in ("sort_date", "sort_journal_partner") else "sort_date",
            "sort_selection": options.get("sort_selection") if options.get("sort_selection") in ("date", "move_name") else "move_name",
            "reconciled": bool(options.get("reconciled")),
            "amount_currency": bool(options.get("amount_currency")),
            "journal_ids": journal_ids,
            "account_ids": account_ids,
            "account_search": options.get("account_search") or "",
            "period_length": int(options.get("period_length") or 30),
            "period": options.get("period") or ("month" if report_key == "trial_balance" else "year"),
            "anchor_date": options.get("anchor_date") or fields.Date.to_string(default_to),
            "currency_label": self.env.company.currency_id.name or self.env.company.currency_id.symbol,
        }

    # ------------------------------------------------------------------
    # Comparison-period helpers (ported from AimAze accounting kit)
    # ------------------------------------------------------------------

    @api.model
    def _format_period_label(self, p_from, p_to):
        """A clean calendar month collapses to "Jun 2026"; otherwise show the range."""
        month_end = (p_from + relativedelta(months=1)) - timedelta(days=1)
        if p_from.day == 1 and p_to == month_end:
            return p_from.strftime("%b %Y")
        if p_from == date(p_from.year, 1, 1) and p_to == date(p_from.year, 12, 31):
            return p_from.strftime("%Y")
        if p_from.year == p_to.year:
            return f"{p_from.strftime('%d %b')} – {p_to.strftime('%d %b %Y')}"
        return f"{p_from.strftime('%d %b %Y')} – {p_to.strftime('%d %b %Y')}"

    @api.model
    def _comparison_button_label(self, comparison, count, cmp_from_str, cmp_to_str):
        """Text shown on the Comparison toolbar button."""
        if comparison == "none":
            return ""
        if comparison == "previous_period":
            return _("%s Previous Period", count) if count == 1 else _("%s Previous Periods", count)
        if comparison == "same_last_year":
            return _("%s Previous Year", count) if count == 1 else _("%s Previous Years", count)
        if cmp_from_str and cmp_to_str:
            return self._format_period_label(
                fields.Date.from_string(cmp_from_str), fields.Date.from_string(cmp_to_str)
            )
        return _("Custom")

    @api.model
    def _period_kind(self, d_from, d_to):
        """Classify a date range as 'year' / 'quarter' / 'month' / 'custom'."""
        if d_from == date(d_from.year, 1, 1) and d_to == date(d_from.year, 12, 31):
            return "year"
        q_start_month = ((d_from.month - 1) // 3) * 3 + 1
        if d_from.day == 1 and d_from.month == q_start_month:
            q_end_month = q_start_month + 2
            if d_to == date(d_from.year, q_end_month, calendar.monthrange(d_from.year, q_end_month)[1]):
                return "quarter"
        if d_from.day == 1 and d_to == (d_from + relativedelta(day=31)):
            return "month"
        return "custom"

    @api.model
    def _shift_calendar_period(self, d_from, kind, units):
        """Return (from, to) for the calendar period `units` steps before d_from."""
        if kind == "year":
            nf = d_from - relativedelta(years=units)
            return nf, nf + relativedelta(month=12, day=31)
        if kind == "quarter":
            nf = d_from - relativedelta(months=3 * units)
            return nf, nf + relativedelta(months=2, day=31)
        nf = d_from - relativedelta(months=units)
        return nf, nf + relativedelta(day=31)

    @api.model
    def _comparison_periods(self, options):
        """Ordered list of periods to render (oldest first, current period last).

        Each entry is ``{key, label, date_from, date_to, is_current}``. With no
        comparison only the current period is returned.
        """
        d_from = fields.Date.from_string(options["date_from"])
        d_to = fields.Date.from_string(options["date_to"])
        kind = self._period_kind(d_from, d_to)
        current = {
            "key": "p0",
            "label": self._format_period_label(d_from, d_to),
            "date_from": d_from,
            "date_to": d_to,
            "is_current": True,
        }
        comparison = options.get("comparison") or "none"
        count = int(options.get("comparison_count") or 1)
        comparisons = []
        if comparison == "previous_period":
            if kind in ("year", "quarter", "month"):
                for i in range(1, count + 1):
                    comparisons.append(self._shift_calendar_period(d_from, kind, i))
            elif d_from.day == 1 and d_from.year == d_to.year and d_from.month == d_to.month:
                # Month-to-date: keep the same day-span in each prior month.
                for i in range(1, count + 1):
                    p_from = d_from - relativedelta(months=i)
                    p_to = p_from + relativedelta(day=d_to.day)
                    comparisons.append((p_from, p_to))
            else:
                span = d_to - d_from
                cur_from = d_from
                for i in range(1, count + 1):
                    p_to = cur_from - timedelta(days=1)
                    p_from = p_to - span
                    comparisons.append((p_from, p_to))
                    cur_from = p_from
        elif comparison == "same_last_year":
            for i in range(1, count + 1):
                comparisons.append((d_from - relativedelta(years=i), d_to - relativedelta(years=i)))
        elif comparison == "custom":
            raw_from = options.get("comparison_date_from")
            raw_to = options.get("comparison_date_to")
            if raw_from and raw_to:
                c_from = fields.Date.from_string(raw_from)
                c_to = fields.Date.from_string(raw_to)
                if c_to < c_from:
                    c_from, c_to = c_to, c_from
                comparisons.append((c_from, c_to))
        periods = []
        for idx, (p_from, p_to) in enumerate(comparisons, start=1):
            periods.append({
                "key": f"c{idx}",
                "label": self._format_period_label(p_from, p_to),
                "date_from": p_from,
                "date_to": p_to,
                "is_current": False,
            })
        periods.sort(key=lambda p: p["date_from"])
        periods.append(current)
        return periods

    @api.model
    def _statement_periods(self, report_key, options):
        """Ordered comparison periods for a Balance Sheet / P&L statement."""
        periods = self._comparison_periods(options)
        if report_key == "balance_sheet":
            for period in periods:
                period["label"] = _("As of %s") % period["date_to"].strftime("%m/%d/%Y")
        reverse = (options.get("period_order") or "descending") == "descending"
        return sorted(periods, key=lambda p: p["date_from"], reverse=reverse)

    @api.model
    def _statement_with_comparison(self, report_key, options, builder):
        """Build a statement, then append one balance column per comparison period."""
        columns, lines = builder(options)
        if (options.get("comparison") or "none") == "none":
            return columns, lines
        periods = self._statement_periods(report_key, options)
        comparison_periods = [p for p in periods if not p.get("is_current")]
        if not comparison_periods:
            return columns, lines
        new_columns = [c for c in columns if c["key"] == "name"]
        for period in periods:
            key = "balance" if period.get("is_current") else f"cmp_{period['key']}"
            new_columns.append({"key": key, "label": period["label"], "type": "number"})
        for period in periods:
            if period.get("is_current"):
                continue
            p_options = dict(options)
            p_options["comparison"] = "none"
            p_options["date_from"] = fields.Date.to_string(period["date_from"])
            p_options["date_to"] = fields.Date.to_string(period["date_to"])
            _cols, p_lines = builder(p_options)
            by_id = {line["id"]: line["values"].get("balance", 0.0) for line in p_lines}
            key = f"cmp_{period['key']}"
            for line in lines:
                line["values"][key] = by_id.get(line["id"], 0.0)
        # A single comparison period also gets a growth % column.
        if len(comparison_periods) == 1:
            cmp_key = f"cmp_{comparison_periods[0]['key']}"
            for line in lines:
                current = line["values"].get("balance", 0.0)
                previous = line["values"].get(cmp_key, 0.0)
                line["values"]["cmp_pct"] = (
                    (current - previous) / abs(previous) * 100.0 if abs(previous) >= 0.005 else None
                )
            new_columns.append({"key": "cmp_pct", "label": _("%"), "type": "percent"})
        # 2+ comparison periods: append a Total column summing every shown period.
        if len(comparison_periods) >= 2:
            period_value_keys = [
                "balance" if p.get("is_current") else f"cmp_{p['key']}" for p in periods
            ]
            for line in lines:
                line["values"]["period_total"] = sum(
                    (line["values"].get(k) or 0.0) for k in period_value_keys
                )
            new_columns.append({"key": "period_total", "label": _("Total"), "type": "number"})
        return new_columns, lines

    @api.model
    def _selected_journal_ids(self, options):
        return options.get("journal_ids") or [journal["id"] for journal in self._journal_payload()]

    @api.model
    def _journal_ids_for_type(self, options, journal_type=None):
        if options.get("journal_ids"):
            return options["journal_ids"]
        domain = [("company_id", "=", self.env.company.id)]
        if journal_type:
            domain.append(("type", "=", journal_type))
        return self.env["account.journal"].search(domain).ids

    @api.model
    def _journal_payload(self):
        journals = self.env["account.journal"].search([("company_id", "=", self.env.company.id)], order="name")
        return [{"id": journal.id, "name": journal.display_name, "code": journal.code} for journal in journals]

    @api.model
    def _journal_label(self, options):
        if not options.get("journal_ids"):
            return _("All Journals")
        journals = self.env["account.journal"].browse(options["journal_ids"])
        return ", ".join(journals.mapped("code")) or _("Selected Journals")

    @api.model
    def _financial_wizard_data(self, report_key, options):
        config = self.FINANCIAL_REPORTS[report_key]
        report = self.env.ref(config["xmlid"])
        wizard_model = "cash.flow.report" if config.get("cash_flow") else "financial.report"
        vals = {
            "account_report_id": report.id,
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "debit_credit": options["debit_credit"],
            "enable_filter": options["enable_filter"],
            "company_id": self.env.company.id,
        }
        if config.get("cash_flow"):
            vals["journal_ids"] = [(6, 0, self._selected_journal_ids(options))]
        wizard = self.env[wizard_model].create(vals)
        fields_to_read = [
            "date_from", "enable_filter", "debit_credit", "date_to",
            "account_report_id", "target_move", "company_id",
        ]
        if config.get("cash_flow"):
            fields_to_read += ["journal_ids", "filter_cmp", "label_filter", "date_from_cmp", "date_to_cmp"]
        data = {
            "ids": [],
            "model": "ir.ui.menu",
            "form": wizard.read(fields_to_read)[0],
        }
        data["form"]["journal_ids"] = options.get("journal_ids") or False
        used_context = wizard._build_contexts(data)
        data["form"]["used_context"] = dict(used_context, lang=get_lang(self.env).code)
        if config.get("cash_flow"):
            data["form"]["comparison_context"] = {}
            report_lines = self.env["report.base_accounting_kit.report_cash_flow"].get_account_lines(data["form"])
            data["account_report_id"] = data["form"]["account_report_id"]
            data.update(data["form"])
        else:
            report_lines = wizard.get_account_lines(data["form"])
            data["journal_items"] = wizard.find_journal_items(report_lines, data["form"])
            data["report_lines"] = report_lines
            data["currency"] = wizard._get_currency()
        return wizard, data, report_lines

    @api.model
    def _financial_report(self, report_key, options):
        if report_key == "profit_and_loss":
            return self._statement_with_comparison(report_key, options, self._profit_and_loss_statement)
        if report_key == "balance_sheet":
            return self._statement_with_comparison(report_key, options, self._balance_sheet_statement)
        if report_key == "cash_flow":
            return self._cash_flow_statement(options)
        _wizard, _data, report_lines = self._financial_wizard_data(report_key, options)
        columns = [{"key": "name", "label": _("Name"), "type": "text"}]
        if options["debit_credit"]:
            columns += [
                {"key": "debit", "label": _("Debit"), "type": "number"},
                {"key": "credit", "label": _("Credit"), "type": "number"},
            ]
        columns.append({"key": "balance", "label": _("Balance"), "type": "number"})
        return columns, self._line_payload(report_lines)

    @api.model
    def _statement_columns(self, options):
        columns = [{"key": "name", "label": "", "type": "text"}]
        if options["debit_credit"]:
            columns += [
                {"key": "debit", "label": _("Debit"), "type": "number"},
                {"key": "credit", "label": _("Credit"), "type": "number"},
            ]
        columns.append({"key": "balance", "label": _("Balance"), "type": "number"})
        return columns

    @api.model
    def _move_line_domain(self, options, account_ids=False, account_types=False, date_from=True):
        domain = [("company_id", "=", self.env.company.id)]
        if account_ids:
            domain.append(("account_id", "in", account_ids))
        if account_types:
            domain.append(("account_id.account_type", "in", account_types))
        if date_from and options.get("date_from"):
            domain.append(("date", ">=", options["date_from"]))
        if options.get("date_to"):
            domain.append(("date", "<=", options["date_to"]))
        if options.get("target_move") == "posted":
            domain.append(("move_id.state", "=", "posted"))
        if options.get("journal_ids"):
            domain.append(("journal_id", "in", options["journal_ids"]))
        return domain

    @api.model
    def _move_line_action(self, name, options, account_ids=False, account_types=False, date_from=True):
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": self._move_line_domain(
                options,
                account_ids=account_ids,
                account_types=account_types,
                date_from=date_from,
            ),
            "context": {
                "search_default_group_by_move": 1,
                "default_company_id": self.env.company.id,
            },
        }

    @api.model
    def _line_action_general_ledger(self):
        return [{"key": "general_ledger", "label": _("General Ledger")}]

    @api.model
    def _line_action_journal_entry(self):
        return [{"key": "journal_entry", "label": _("View Journal Entry")}]

    @api.model
    def _account_balances(self, account_types, options, sign=1, date_from=True):
        accounts = self.env["account.account"].search(
            [
                ("company_ids", "in", [self.env.company.id]),
                ("account_type", "in", account_types),
            ],
            order="code, name",
        )
        if not accounts:
            return [], {"debit": 0.0, "credit": 0.0, "balance": 0.0}, []
        rows = self.env["account.move.line"]._read_group(
            domain=self._move_line_domain(options, account_ids=accounts.ids, date_from=date_from),
            groupby=["account_id"],
            aggregates=["debit:sum", "credit:sum", "balance:sum"],
        )
        grouped = {
            account.id: {
                "debit": debit_sum,
                "credit": credit_sum,
                "balance": balance_sum,
            }
            for account, debit_sum, credit_sum, balance_sum in rows
        }
        account_lines = []
        totals = {"debit": 0.0, "credit": 0.0, "balance": 0.0}
        for account in accounts:
            values = grouped.get(account.id)
            if not values:
                continue
            debit = values.get("debit") or 0.0
            credit = values.get("credit") or 0.0
            raw_balance = values.get("balance") or 0.0
            balance = raw_balance * sign
            if not any(abs(value) >= 0.005 for value in (debit, credit, balance)):
                continue
            totals["debit"] += debit
            totals["credit"] += credit
            totals["balance"] += balance
            account_lines.append(
                {
                    "id": f"account_{account.id}",
                    "name": f"{account.code or ''} {account.name or ''}".strip(),
                    "level": 2,
                    "type": "account",
                    "account_id": account.id,
                    "account_code": account.code or "",
                    "line_actions": self._line_action_general_ledger(),
                    "is_total": False,
                    "parent_id": False,
                    "values": {
                        "name": f"{account.code or ''} {account.name or ''}".strip(),
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                    },
                }
            )
        return account_lines, totals, accounts.ids

    @api.model
    def _section_line(self, key, name, totals, children, options, account_types, sign=1, account_ids=None):
        for child in children:
            child["id"] = f"{key}_{child['id']}"
            child["parent_id"] = key
        ids = list(account_ids or [])
        if not ids and children:
            ids = [c["account_id"] for c in children if c.get("account_id")]
        line = {
            "id": key,
            "name": name,
            "level": 1,
            "type": "section",
            "is_total": False,
            "unfoldable": bool(children),
            "default_unfolded": bool(children),
            "values": {
                "name": name,
                "debit": totals["debit"],
                "credit": totals["credit"],
                "balance": totals["balance"] * sign,
            },
        }
        if ids:
            line["account_ids"] = ids
            line["line_actions"] = self._line_action_general_ledger()
        return line

    @api.model
    def _total_line(self, key, name, amount, debit=0.0, credit=0.0, level=1, grand=False, account_ids=None):
        line = {
            "id": key,
            "name": name,
            "level": level,
            "type": "total",
            "is_total": True,
            "is_grand_total": grand,
            "values": {
                "name": name,
                "debit": debit,
                "credit": credit,
                "balance": amount,
            },
        }
        if account_ids:
            line["account_ids"] = list(account_ids)
            line["line_actions"] = self._line_action_general_ledger()
        return line

    @api.model
    def _statement_note_line(self, key, name, amount, level=2):
        return {
            "id": key,
            "name": name,
            "level": level,
            "type": "account",
            "is_total": False,
            "values": {
                "name": name,
                "debit": 0.0,
                "credit": 0.0,
                "balance": amount,
            },
        }

    @api.model
    def _profit_and_loss_totals(self, options):
        _revenue_lines, revenue, _revenue_account_ids = self._account_balances(["income"], options, sign=-1)
        _cost_lines, cost, _cost_account_ids = self._account_balances(["expense_direct_cost"], options, sign=1)
        _expense_lines, expenses, _expense_account_ids = self._account_balances(
            ["expense", "expense_depreciation"], options, sign=1
        )
        _other_income_lines, other_income, _other_income_account_ids = self._account_balances(
            ["income_other"], options, sign=-1
        )
        gross_profit = revenue["balance"] - cost["balance"]
        operating_income = gross_profit - expenses["balance"]
        net_profit = operating_income + other_income["balance"]
        return {
            "revenue": revenue,
            "cost": cost,
            "expenses": expenses,
            "other_income": other_income,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "net_profit": net_profit,
        }

    @api.model
    def _profit_and_loss_statement(self, options):
        revenue_lines, revenue, revenue_account_ids = self._account_balances(["income"], options, sign=-1)
        cost_lines, cost, cost_account_ids = self._account_balances(["expense_direct_cost"], options, sign=1)
        expense_lines, expenses, expense_account_ids = self._account_balances(
            ["expense", "expense_depreciation"], options, sign=1
        )
        other_income_lines, other_income, other_income_account_ids = self._account_balances(
            ["income_other"], options, sign=-1
        )
        gross_profit = revenue["balance"] - cost["balance"]
        operating_income = gross_profit - expenses["balance"]
        net_profit = operating_income + other_income["balance"]
        lines = []
        revenue_section = self._section_line("revenue", _("Revenue"), revenue, revenue_lines, options, ["income"], account_ids=revenue_account_ids)
        cost_section = self._section_line(
            "cost_of_revenue",
            _("Less Cost of Revenue"),
            cost,
            cost_lines,
            options,
            ["expense_direct_cost"],
            account_ids=cost_account_ids,
        )
        expense_section = self._section_line(
            "operating_expenses",
            _("Less Operating Expenses"),
            expenses,
            expense_lines,
            options,
            ["expense", "expense_depreciation"],
            account_ids=expense_account_ids,
        )
        other_income_section = self._section_line(
            "other_income",
            _("Plus Other Income"),
            other_income,
            other_income_lines,
            options,
            ["income_other"],
            account_ids=other_income_account_ids,
        )
        gross_profit_ids = list(revenue_account_ids) + list(cost_account_ids)
        operating_ids = gross_profit_ids + list(expense_account_ids)
        net_profit_ids = operating_ids + list(other_income_account_ids)
        lines += [revenue_section] + revenue_lines
        lines += [cost_section] + cost_lines
        lines.append(self._total_line("gross_profit", _("Gross Profit"), gross_profit, account_ids=gross_profit_ids))
        lines += [expense_section] + expense_lines
        lines.append(self._total_line("operating_income", _("Operating Income (or Loss)"), operating_income, account_ids=operating_ids))
        lines += [other_income_section] + other_income_lines
        lines.append(self._statement_note_line("other_expenses", _("Less Other Expenses"), 0.0, level=1))
        lines.append(self._total_line("net_profit", _("Net Profit"), net_profit, account_ids=net_profit_ids))
        lines.append(
            self._statement_note_line(
                "allocations_withdrawals",
                _("Less Allocations and Plus Withdrawals"),
                0.0,
                level=1,
            )
        )
        lines.append(
            self._total_line(
                "net_profit_after_allocations",
                _("Net Profit Left After Allocations and Withdrawals"),
                net_profit,
                grand=True,
                account_ids=net_profit_ids,
            )
        )
        return self._statement_columns(options), lines

    @api.model
    def _cash_opening_balance(self, options):
        opening_options = dict(options)
        opening_options["date_from"] = False
        if options.get("date_from"):
            date_from = fields.Date.from_string(options["date_from"])
            opening_options["date_to"] = fields.Date.to_string(date_from - timedelta(days=1))
        _lines, totals, _account_ids = self._account_balances(["asset_cash"], opening_options, sign=1, date_from=False)
        return totals

    @api.model
    def _cash_flow_statement(self, options):
        pnl_account_types = [
            "income",
            "income_other",
            "expense",
            "expense_direct_cost",
            "expense_depreciation",
        ]
        operating_specs = [
            ("receivables", _("Change in Receivables"), ["asset_receivable"], -1),
            (
                "operating_assets",
                _("Change in Inventory, Prepayments and Other Current Assets"),
                ["asset_current", "asset_prepayments"],
                -1,
            ),
            ("payables", _("Change in Payables"), ["liability_payable"], -1),
            (
                "current_liabilities",
                _("Change in Tax and Other Current Liabilities"),
                ["liability_current", "liability_credit_card"],
                -1,
            ),
        ]
        investing_specs = [
            (
                "fixed_assets",
                _("Purchase / Sale of Fixed and Non-current Assets"),
                ["asset_fixed", "asset_non_current"],
                -1,
            ),
        ]
        financing_specs = [
            ("loans", _("Change in Loans and Non-current Liabilities"), ["liability_non_current"], -1),
            ("equity", _("Capital, Drawings and Retained Earnings Movement"), ["equity", "equity_unaffected"], -1),
        ]

        pnl_totals = self._profit_and_loss_totals(options)
        operating_children = [
            self._statement_note_line(
                "net_profit_before_working_capital",
                _("Net Profit before Working Capital Changes"),
                pnl_totals["net_profit"],
            )
        ]
        operating_total = pnl_totals["net_profit"]
        operating_account_types = list(pnl_account_types)

        for key, label, account_types, sign in operating_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=sign)
            for line in account_lines:
                line["id"] = f"{key}_{line['id']}"
                line["name"] = label if len(account_lines) == 1 else line["name"]
                line["values"]["name"] = line["name"]
            operating_children += account_lines
            operating_total += totals["balance"]
            operating_account_types += account_types

        operating_section = self._section_line(
            "operating_activities",
            _("Cash Flows from Operating Activities"),
            {"debit": 0.0, "credit": 0.0, "balance": operating_total},
            operating_children,
            options,
            operating_account_types,
        )

        investing_children = []
        investing_total = 0.0
        investing_account_types = []
        for key, label, account_types, sign in investing_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=sign)
            for line in account_lines:
                line["id"] = f"{key}_{line['id']}"
                line["name"] = label if len(account_lines) == 1 else line["name"]
                line["values"]["name"] = line["name"]
            investing_children += account_lines
            investing_total += totals["balance"]
            investing_account_types += account_types
        investing_section = self._section_line(
            "investing_activities",
            _("Cash Flows from Investing Activities"),
            {"debit": 0.0, "credit": 0.0, "balance": investing_total},
            investing_children,
            options,
            investing_account_types,
        )

        financing_children = []
        financing_total = 0.0
        financing_account_types = []
        for key, label, account_types, sign in financing_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=sign)
            for line in account_lines:
                line["id"] = f"{key}_{line['id']}"
                line["name"] = label if len(account_lines) == 1 else line["name"]
                line["values"]["name"] = line["name"]
            financing_children += account_lines
            financing_total += totals["balance"]
            financing_account_types += account_types
        financing_section = self._section_line(
            "financing_activities",
            _("Cash Flows from Financing Activities"),
            {"debit": 0.0, "credit": 0.0, "balance": financing_total},
            financing_children,
            options,
            financing_account_types,
        )

        _cash_lines, cash_change, _cash_account_ids = self._account_balances(["asset_cash"], options, sign=1)
        classified_cash_change = operating_total + investing_total + financing_total
        balancing_amount = cash_change["balance"] - classified_cash_change
        opening_cash = self._cash_opening_balance(options)["balance"]
        closing_cash = opening_cash + cash_change["balance"]

        lines = [operating_section] + operating_children
        lines.append(self._total_line("net_operating_cash", _("Net Cash Provided by Operating Activities"), operating_total))
        lines += [investing_section] + investing_children
        lines.append(self._total_line("net_investing_cash", _("Net Cash Used in Investing Activities"), investing_total))
        lines += [financing_section] + financing_children
        lines.append(self._total_line("net_financing_cash", _("Net Cash from Financing Activities"), financing_total))
        if abs(balancing_amount) >= 0.005:
            lines.append(
                self._statement_note_line(
                    "other_cash_movement",
                    _("Other / Unclassified Cash Movement"),
                    balancing_amount,
                    level=1,
                )
            )
        lines.append(self._total_line("net_cash_change", _("Net Increase / (Decrease) in Cash"), cash_change["balance"], grand=True))
        lines.append(self._total_line("opening_cash", _("Cash at Beginning of Period"), opening_cash))
        lines.append(self._total_line("closing_cash", _("Cash at End of Period"), closing_cash, grand=True))
        return self._statement_columns(options), lines

    @api.model
    def _balance_sheet_statement(self, options):
        asset_specs = [
            ("cash", _("Bank and Cash"), ["asset_cash"]),
            ("receivables", _("Receivables"), ["asset_receivable"]),
            ("current_assets", _("Current Assets"), ["asset_current", "asset_prepayments"]),
            ("fixed_assets", _("Fixed and Non-current Assets"), ["asset_fixed", "asset_non_current"]),
        ]
        liability_specs = [
            ("payables", _("Payables"), ["liability_payable"]),
            ("current_liabilities", _("Current Liabilities"), ["liability_current", "liability_credit_card"]),
            ("non_current_liabilities", _("Non-current Liabilities"), ["liability_non_current"]),
        ]
        equity_specs = [
            ("equity", _("Equity"), ["equity", "equity_unaffected"]),
        ]
        lines = []
        total_assets = 0.0
        for key, label, account_types in asset_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=1, date_from=False)
            section = self._section_line(key, label, totals, account_lines, options, account_types)
            total_assets += totals["balance"]
            lines += [section] + account_lines
        lines.append(self._total_line("total_assets", _("Total Assets"), total_assets, grand=True))

        total_liabilities = 0.0
        for key, label, account_types in liability_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=-1, date_from=False)
            section = self._section_line(key, label, totals, account_lines, options, account_types)
            total_liabilities += totals["balance"]
            lines += [section] + account_lines
        lines.append(self._total_line("total_liabilities", _("Total Liabilities"), total_liabilities, grand=True))

        total_equity = 0.0
        for key, label, account_types in equity_specs:
            account_lines, totals, _account_ids = self._account_balances(account_types, options, sign=-1, date_from=False)
            section = self._section_line(key, label, totals, account_lines, options, account_types)
            total_equity += totals["balance"]
            lines += [section] + account_lines
        net_profit = self._profit_and_loss_totals(options)["net_profit"]
        lines.append(
            {
                "id": "current_year_earnings",
                "name": _("Current Year Earnings"),
                "level": 2,
                "type": "account",
                "is_total": False,
                "values": {
                    "name": _("Current Year Earnings"),
                    "debit": 0.0,
                    "credit": 0.0,
                    "balance": net_profit,
                },
            }
        )
        total_equity += net_profit
        lines.append(self._total_line("total_equity", _("Total Equity"), total_equity, grand=True))
        lines.append(
            self._total_line(
                "total_liabilities_equity",
                _("Total Liabilities and Equity"),
                total_liabilities + total_equity,
                grand=True,
            )
        )
        return self._statement_columns(options), lines

    @api.model
    def _line_payload(self, report_lines):
        payload = []
        for index, line in enumerate(report_lines):
            level = int(line.get("level") or 1)
            payload.append({
                "id": line.get("id") or line.get("a_id") or f"line_{index}",
                "name": line.get("name") or "",
                "level": level,
                "type": line.get("type") or "report",
                "is_total": level <= 2 and line.get("type") == "report",
                "values": {
                    "name": line.get("name") or "",
                    "debit": line.get("debit") or 0.0,
                    "credit": line.get("credit") or 0.0,
                    "balance": line.get("balance") or 0.0,
                    "balance_cmp": line.get("balance_cmp") or 0.0,
                },
            })
        return payload

    @api.model
    def _trial_balance_report(self, options):
        currency = self.env.company.currency_id
        account_domain = [("company_ids", "in", [self.env.company.id])]
        accounts = self.env["account.account"].search(account_domain, order="code, name")

        initial_balances = self._trial_balance_group(
            accounts,
            [
                ("date", "<", options["date_from"]),
            ],
            options,
            aggregates=["balance:sum"],
        )
        period_balances = self._trial_balance_group(
            accounts,
            [
                ("date", ">=", options["date_from"]),
                ("date", "<=", options["date_to"]),
            ],
            options,
            aggregates=["debit:sum", "credit:sum", "balance:sum"],
        )

        columns = [
            {"key": "name", "label": _(""), "type": "text"},
            {"key": "initial_balance", "label": _("Balance"), "type": "number"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
            {"key": "end_balance", "label": _("Balance"), "type": "number"},
        ]

        totals = {
            "initial_balance": 0.0,
            "debit": 0.0,
            "credit": 0.0,
            "end_balance": 0.0,
        }
        lines = []
        for account in accounts:
            initial_balance = initial_balances.get(account.id, {}).get("balance") or 0.0
            period_values = period_balances.get(account.id, {})
            debit = period_values.get("debit") or 0.0
            credit = period_values.get("credit") or 0.0
            end_balance = initial_balance + (period_values.get("balance") or 0.0)

            if options["display_account"] == "movement":
                visible = any(not currency.is_zero(value) for value in (initial_balance, debit, credit, end_balance))
            elif options["display_account"] == "not_zero":
                visible = not currency.is_zero(end_balance)
            else:
                visible = True
            if not visible:
                continue

            values = {
                "name": f"{account.code or ''} {account.name or ''}".strip(),
                "initial_balance": initial_balance,
                "debit": debit,
                "credit": credit,
                "end_balance": end_balance,
            }
            for key in totals:
                totals[key] += values[key]
            lines.append({
                "id": f"account_{account.id}",
                "name": values["name"],
                "level": 1,
                "type": "account",
                "account_id": account.id,
                "account_code": account.code or "",
                "line_actions": self._line_action_general_ledger(),
                "is_total": False,
                "values": values,
            })

        if any(not currency.is_zero(totals[key]) for key in ("initial_balance", "end_balance")):
            carry_values = {
                "name": _("Result Brought Forward"),
                "initial_balance": -totals["initial_balance"],
                "debit": 0.0,
                "credit": 0.0,
                "end_balance": -totals["end_balance"],
            }
            for key in totals:
                totals[key] += carry_values[key]
            lines.append({
                "id": "result_brought_forward",
                "name": carry_values["name"],
                "level": 1,
                "type": "carry_forward",
                "is_total": False,
                "values": carry_values,
            })

        lines.append({
            "id": "trial_balance_total",
            "name": _("Total"),
            "level": 1,
            "type": "total",
            "is_total": True,
            "values": {
                "name": _("Total"),
                **totals,
            },
        })
        return columns, lines

    @api.model
    def _trial_balance_group(self, accounts, domain, options, aggregates):
        if not accounts:
            return {}
        full_domain = [
            ("company_id", "=", self.env.company.id),
            ("account_id", "in", accounts.ids),
            *domain,
        ]
        if options.get("target_move") == "posted":
            full_domain.append(("move_id.state", "=", "posted"))
        if options.get("journal_ids"):
            full_domain.append(("journal_id", "in", options["journal_ids"]))
        rows = self.env["account.move.line"]._read_group(
            domain=full_domain,
            groupby=["account_id"],
            aggregates=aggregates,
        )
        result = {}
        for row in rows:
            account = row[0]
            values = {}
            for index, aggregate in enumerate(aggregates, start=1):
                values[aggregate.split(":", 1)[0]] = row[index] or 0.0
            result[account.id] = values
        return result

    @api.model
    def _general_ledger_report(self, options):
        journals = self._selected_journal_ids(options)
        wizard = self.env["account.report.general.ledger"].create({
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "display_account": options["display_account"],
            "company_id": self.env.company.id,
            "initial_balance": options["initial_balance"],
            "sortby": options["sortby"],
            "journal_ids": [(6, 0, journals)],
        })
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
        elif options.get("account_search"):
            account_domain += [
                "|",
                ("code", "ilike", options["account_search"]),
                ("name", "ilike", options["account_search"]),
            ]
        accounts = self.env["account.account"].search(account_domain, order="code, name")
        account_lines = self.env["report.base_accounting_kit.report_general_ledger"].with_context(
            data["form"]["used_context"]
        )._get_account_move_entry(accounts, options["initial_balance"], options["sortby"], options["display_account"])
        columns = [
            {"key": "name", "label": "", "type": "text"},
            {"key": "date", "label": _("Date"), "type": "text"},
            {"key": "partner", "label": _("Partner"), "type": "text"},
            {"key": "currency", "label": _("Currency"), "type": "text"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
            {"key": "balance", "label": _("Balance"), "type": "number"},
        ]
        lines = []
        for index, account in enumerate(account_lines):
            account_id = f"account_{index}"
            account_label = f"{account.get('code') or ''} {account.get('name') or ''}".strip()
            lines.append({
                "id": account_id,
                "name": account_label,
                "level": 1,
                "type": "account",
                "account_id": account.get("id"),
                "account_code": account.get("code") or "",
                "is_total": True,
                "values": {
                    "name": account_label,
                    "date": "",
                    "partner": "",
                    "currency": "",
                    "debit": account.get("debit") or 0.0,
                    "credit": account.get("credit") or 0.0,
                    "balance": account.get("balance") or 0.0,
                },
            })
            for move_index, move in enumerate(account.get("move_lines") or []):
                move_id = move.get("move_id")
                entry_parts = []
                for part in (move.get("move_name"), move.get("lname")):
                    if part and part not in ("/", "False") and part not in entry_parts:
                        entry_parts.append(part)
                entry_label = " ".join(entry_parts) or move.get("lname") or move.get("move_name") or ""
                lines.append({
                    "id": f"{account_id}_{move_index}",
                    "name": entry_label,
                    "level": 2,
                    "type": "move",
                    "move_id": move_id,
                    "move_line_id": move.get("lid"),
                    "line_actions": self._line_action_journal_entry() if move_id else [],
                    "is_total": False,
                    "values": {
                        "name": entry_label,
                        "date": fields.Date.to_string(move.get("ldate")) if move.get("ldate") else "",
                        "partner": move.get("partner_name") or "",
                        "currency": move.get("currency_code") or options.get("currency_label") or "",
                        "debit": move.get("debit") or 0.0,
                        "credit": move.get("credit") or 0.0,
                        "balance": move.get("balance") or 0.0,
                    },
                })
        return columns, lines

    @api.model
    def _partner_ledger_report(self, options):
        journals = self._selected_journal_ids(options)
        wizard = self.env["account.report.partner.ledger"].create({
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "result_selection": options["result_selection"],
            "company_id": self.env.company.id,
            "journal_ids": [(6, 0, journals)],
            "reconciled": options["reconciled"],
            "amount_currency": options["amount_currency"],
        })
        data = {
            "ids": [],
            "model": "ir.ui.menu",
            "form": wizard.read(["date_from", "date_to", "journal_ids", "target_move", "company_id"])[0],
        }
        data["form"].update(wizard.read(["result_selection", "reconciled", "amount_currency"])[0])
        data["form"]["used_context"] = dict(wizard._build_contexts(data), lang=get_lang(self.env).code)
        report_model = self.env["report.base_accounting_kit.report_partnerledger"]
        report_values = report_model._get_report_values([], data=data)
        columns = [
            {"key": "date", "label": _("Date"), "type": "text"},
            {"key": "name", "label": _("Partner / Entry"), "type": "text"},
            {"key": "journal", "label": _("Journal"), "type": "text"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
            {"key": "balance", "label": _("Balance"), "type": "number"},
        ]
        lines = []
        for partner in report_values["docs"]:
            debit = report_values["sum_partner"](data, partner, "debit") or 0.0
            credit = report_values["sum_partner"](data, partner, "credit") or 0.0
            balance = report_values["sum_partner"](data, partner, "debit - credit") or 0.0
            partner_id = f"partner_{partner.id}"
            lines.append({
                "id": partner_id,
                "name": partner.display_name,
                "level": 1,
                "type": "partner",
                "is_total": True,
                "values": {"date": "", "name": partner.display_name, "journal": "", "debit": debit, "credit": credit, "balance": balance},
            })
            for index, move in enumerate(report_values["lines"](data, partner)):
                lines.append({
                    "id": f"{partner_id}_{index}",
                    "name": move.get("displayed_name") or "",
                    "level": 2,
                    "type": "move",
                    "is_total": False,
                    "values": {
                        "date": fields.Date.to_string(move.get("date")) if move.get("date") else "",
                        "name": move.get("displayed_name") or "",
                        "journal": move.get("code") or "",
                        "debit": move.get("debit") or 0.0,
                        "credit": move.get("credit") or 0.0,
                        "balance": move.get("progress") or 0.0,
                    },
                })
        return columns, lines

    @api.model
    def _tax_report(self, options):
        journals = self._selected_journal_ids(options)
        wizard = self.env["kit.account.tax.report"].create({
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "company_id": self.env.company.id,
            "journal_ids": [(6, 0, journals)],
        })
        data = {
            "ids": [],
            "model": "ir.ui.menu",
            "form": wizard.read(["date_from", "date_to", "journal_ids", "target_move", "company_id"])[0],
        }
        data["form"]["used_context"] = dict(wizard._build_contexts(data), lang=get_lang(self.env).code)
        tax_groups = self.env["report.base_accounting_kit.report_tax"].with_context(
            data["form"]["used_context"]
        ).get_lines(data["form"])
        columns = [
            {"key": "name", "label": _("Tax"), "type": "text"},
            {"key": "net", "label": _("Net"), "type": "number"},
            {"key": "tax", "label": _("Tax"), "type": "number"},
        ]
        lines = []
        for group_key, group_label in (("sale", _("Sales Taxes")), ("purchase", _("Purchase Taxes"))):
            lines.append({
                "id": f"{group_key}_section",
                "name": group_label,
                "level": 1,
                "type": "section",
                "is_total": True,
                "values": {"name": group_label, "net": 0.0, "tax": 0.0},
            })
            for index, line in enumerate(tax_groups.get(group_key, [])):
                lines.append({
                    "id": f"{group_key}_{index}",
                    "name": line.get("name") or "",
                    "level": 2,
                    "type": "tax",
                    "is_total": False,
                    "values": {
                        "name": line.get("name") or "",
                        "net": line.get("net") or 0.0,
                        "tax": line.get("tax") or 0.0,
                    },
                })
        return columns, lines

    @api.model
    def _aged_partner_report(self, options):
        if options["result_selection"] == "customer":
            account_type = ["asset_receivable"]
            report_name = _("Aged Receivable")
        elif options["result_selection"] == "supplier":
            account_type = ["liability_payable"]
            report_name = _("Aged Payable")
        else:
            account_type = ["liability_payable", "asset_receivable"]
            report_name = _("Aged Partner Balance")
        date_from = options["date_to"]
        period_length = max(options["period_length"], 1)
        report_model = self.env["report.base_accounting_kit.report_agedpartnerbalance"]
        partner_lines, totals, _move_lines = report_model._get_partner_move_lines(
            account_type,
            date_from,
            options["target_move"],
            period_length,
        )
        start = fields.Date.from_string(date_from)
        periods = {}
        for index in range(5)[::-1]:
            stop = start - relativedelta(days=period_length)
            period_name = f"{(5 - (index + 1)) * period_length + 1}-{(5 - index) * period_length}"
            if index == 0:
                period_name = f"+{4 * period_length}"
            periods[str(index)] = period_name
            start = stop
        columns = [
            {"key": "name", "label": "", "type": "text"},
            {"key": "invoice_date", "label": _("Invoice Date"), "type": "text"},
            {"key": "direction", "label": _("At Date"), "type": "number"},
            {"key": "4", "label": periods["4"], "type": "number"},
            {"key": "3", "label": periods["3"], "type": "number"},
            {"key": "2", "label": periods["2"], "type": "number"},
            {"key": "1", "label": periods["1"], "type": "number"},
            {"key": "0", "label": _("Older"), "type": "number"},
            {"key": "total", "label": _("Total"), "type": "number"},
        ]
        total_values = {
            "name": report_name,
            "invoice_date": "",
            "direction": totals[6] if len(totals) > 6 else 0.0,
            "4": totals[4] if len(totals) > 4 else 0.0,
            "3": totals[3] if len(totals) > 3 else 0.0,
            "2": totals[2] if len(totals) > 2 else 0.0,
            "1": totals[1] if len(totals) > 1 else 0.0,
            "0": totals[0] if totals else 0.0,
            "total": totals[5] if len(totals) > 5 else 0.0,
        }
        lines = [{
            "id": "aged_total",
            "name": report_name,
            "level": 1,
            "type": "aged_summary",
            "is_total": False,
            "values": total_values,
        }]
        for index, line in enumerate(partner_lines):
            values = {"name": line.get("name") or "", "invoice_date": ""}
            for key in ("direction", "4", "3", "2", "1", "0", "total"):
                values[key] = line.get(key) or 0.0
            action = False
            if line.get("partner_id"):
                action = {
                    "type": "ir.actions.act_window",
                    "name": line.get("name") or _("Partner Entries"),
                    "res_model": "account.move.line",
                    "view_mode": "list,form",
                    "views": [(False, "list"), (False, "form")],
                    "domain": self._move_line_domain(
                        options,
                        account_types=account_type,
                        date_from=False,
                    ) + [("partner_id", "=", line["partner_id"])],
                    "context": {
                        "search_default_group_by_move": 1,
                        "default_company_id": self.env.company.id,
                    },
                }
            lines.append({
                "id": f"aged_{index}",
                "name": values["name"],
                "level": 2,
                "type": "partner",
                "is_total": False,
                "action": action,
                "values": values,
            })
        return columns, lines

    @api.model
    def _journal_audit_report(self, options):
        journals = self._selected_journal_ids(options)
        wizard = self.env["account.print.journal"].create({
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "company_id": self.env.company.id,
            "journal_ids": [(6, 0, journals)],
            "sort_selection": options["sort_selection"],
            "amount_currency": options["amount_currency"],
        })
        data = {
            "ids": [],
            "model": "ir.ui.menu",
            "form": wizard.read(["date_from", "date_to", "journal_ids", "target_move", "company_id"])[0],
        }
        data["form"].update(wizard.read(["amount_currency", "sort_selection"])[0])
        data["form"]["used_context"] = dict(wizard._build_contexts(data), lang=get_lang(self.env).code)
        report_model = self.env["report.base_accounting_kit.report_journal_audit"].with_context(data["form"]["used_context"])
        columns = [
            {"key": "move", "label": _("Move"), "type": "text"},
            {"key": "date", "label": _("Date"), "type": "text"},
            {"key": "account", "label": _("Account"), "type": "text"},
            {"key": "partner", "label": _("Partner"), "type": "text"},
            {"key": "label", "label": _("Label"), "type": "text"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
        ]
        if options["amount_currency"]:
            columns.append({"key": "amount_currency", "label": _("Currency"), "type": "number"})
        lines = []
        for journal in self.env["account.journal"].browse(journals):
            journal_lines = report_model.lines(options["target_move"], journal.id, options["sort_selection"], data)
            debit = report_model._sum_debit(data, journal)
            credit = report_model._sum_credit(data, journal)
            lines.append({
                "id": f"journal_{journal.id}",
                "name": journal.display_name,
                "level": 1,
                "type": "journal",
                "is_total": True,
                "values": {
                    "move": journal.display_name,
                    "date": "",
                    "account": "",
                    "partner": "",
                    "label": _("Total"),
                    "debit": debit,
                    "credit": credit,
                    "amount_currency": 0.0,
                },
            })
            for line in journal_lines:
                values = {
                    "move": line.move_id.name if line.move_id.name != "/" else f"*{line.move_id.id}",
                    "date": fields.Date.to_string(line.date) if line.date else "",
                    "account": line.account_id.code or "",
                    "partner": line.partner_id.display_name if line.partner_id else "",
                    "label": line.name or "",
                    "debit": line.debit or 0.0,
                    "credit": line.credit or 0.0,
                    "amount_currency": line.amount_currency or 0.0,
                }
                lines.append({
                    "id": f"aml_{line.id}",
                    "name": values["label"],
                    "level": 2,
                    "type": "move",
                    "is_total": False,
                    "values": values,
                })
        return columns, lines

    @api.model
    def _daily_book_report(self, options, journal_type=None):
        journal_ids = self._journal_ids_for_type(options, journal_type)
        domain = [
            ("company_id", "=", self.env.company.id),
            ("date", ">=", options["date_from"]),
            ("date", "<=", options["date_to"]),
        ]
        if journal_ids:
            domain.append(("journal_id", "in", journal_ids))
        if options["target_move"] == "posted":
            domain.append(("move_id.state", "=", "posted"))
        order = "date, move_id"
        if options["sortby"] == "sort_journal_partner":
            order = "journal_id, partner_id, date, move_id"
        move_lines = self.env["account.move.line"].search(domain, order=order)
        columns = [
            {"key": "date", "label": _("Date"), "type": "text"},
            {"key": "move", "label": _("Move"), "type": "text"},
            {"key": "journal", "label": _("Journal"), "type": "text"},
            {"key": "account", "label": _("Account"), "type": "text"},
            {"key": "partner", "label": _("Partner"), "type": "text"},
            {"key": "label", "label": _("Label"), "type": "text"},
            {"key": "debit", "label": _("Debit"), "type": "number"},
            {"key": "credit", "label": _("Credit"), "type": "number"},
            {"key": "balance", "label": _("Balance"), "type": "number"},
        ]
        lines = []
        total_debit = sum(move_lines.mapped("debit"))
        total_credit = sum(move_lines.mapped("credit"))
        if move_lines:
            lines.append({
                "id": "daily_total",
                "name": _("Total"),
                "level": 1,
                "type": "total",
                "is_total": True,
                "values": {
                    "date": "",
                    "move": _("Total"),
                    "journal": "",
                    "account": "",
                    "partner": "",
                    "label": "",
                    "debit": total_debit,
                    "credit": total_credit,
                    "balance": total_debit - total_credit,
                },
            })
        for line in move_lines:
            values = {
                "date": fields.Date.to_string(line.date) if line.date else "",
                "move": line.move_id.name or "",
                "journal": line.journal_id.code or "",
                "account": f"{line.account_id.code or ''} {line.account_id.name or ''}".strip(),
                "partner": line.partner_id.display_name if line.partner_id else "",
                "label": line.name or "",
                "debit": line.debit or 0.0,
                "credit": line.credit or 0.0,
                "balance": line.balance or 0.0,
            }
            lines.append({
                "id": f"daily_{line.id}",
                "name": values["label"],
                "level": 2,
                "type": "move",
                "is_total": False,
                "values": values,
            })
        return columns, lines

    @api.model
    def get_report(self, report_key, options=None):
        if report_key not in self.DIRECT_REPORTS:
            report_key = "profit_and_loss"
        options = self._normalize_options(report_key, options)
        config = self.DIRECT_REPORTS[report_key]
        if report_key in self.FINANCIAL_REPORTS:
            columns, lines = self._financial_report(report_key, options)
        elif config.get("kind") == "trial_balance":
            columns, lines = self._trial_balance_report(options)
        elif config.get("kind") == "general_ledger":
            columns, lines = self._general_ledger_report(options)
        elif config.get("kind") == "partner_ledger":
            columns, lines = self._partner_ledger_report(options)
        elif config.get("kind") == "tax_report":
            columns, lines = self._tax_report(options)
        elif config.get("kind") == "aged_partner_balance":
            columns, lines = self._aged_partner_report(options)
        elif config.get("kind") == "journal_audit":
            columns, lines = self._journal_audit_report(options)
        elif config.get("kind") == "daily_book":
            columns, lines = self._daily_book_report(options, config.get("journal_type"))
        else:
            columns, lines = [], []
        return {
            "title": config["title"],
            "report_key": report_key,
            "company": self.env.company.display_name,
            "currency": self.env.company.currency_id.symbol or self.env.company.currency_id.name,
            "currency_label": self.env.company.currency_id.name or self.env.company.currency_id.symbol,
            "options": options,
            "journals": self._journal_payload(),
            "journal_label": self._journal_label(options),
            "target_label": _("Posted Entries") if options["target_move"] == "posted" else _("All Entries"),
            "columns": columns,
            "lines": lines,
        }

    @api.model
    def action_pdf(self, report_key, options=None):
        options = self._normalize_options(report_key, options)
        if report_key in self.FINANCIAL_REPORTS:
            wizard, data, report_lines = self._financial_wizard_data(report_key, options)
            if self.FINANCIAL_REPORTS[report_key].get("cash_flow"):
                return self.env.ref("base_accounting_kit.action_report_cash_flow").report_action(wizard, data=data, config=False)
            data["report_lines"] = report_lines
            return self.env.ref("base_accounting_kit.financial_report_pdf").report_action(wizard, data=data)
        wizard_model = {
            "trial_balance": "account.balance.report",
            "general_ledger": "account.report.general.ledger",
            "partner_ledger": "account.report.partner.ledger",
            "tax_report": "kit.account.tax.report",
            "aged_partner_balance": "account.aged.trial.balance",
            "aged_receivable": "account.aged.trial.balance",
            "aged_payable": "account.aged.trial.balance",
            "journal_audit": "account.print.journal",
            "bank_book": "account.bank.book.report",
            "cash_book": "account.cash.book.report",
            "day_book": "account.day.book.report",
        }.get(report_key)
        if not wizard_model:
            return False
        vals = {
            "date_from": options["date_from"],
            "date_to": options["date_to"],
            "target_move": options["target_move"],
            "company_id": self.env.company.id,
        }
        if report_key in ("trial_balance", "general_ledger"):
            vals["display_account"] = options["display_account"]
        if report_key == "general_ledger":
            vals.update({"initial_balance": options["initial_balance"], "sortby": options["sortby"]})
        if report_key == "partner_ledger":
            vals.update({
                "result_selection": options["result_selection"],
                "reconciled": options["reconciled"],
                "amount_currency": options["amount_currency"],
            })
        if report_key == "tax_report":
            vals["journal_ids"] = [(6, 0, self._selected_journal_ids(options))]
        if report_key in ("aged_partner_balance", "aged_receivable", "aged_payable"):
            vals.update({
                "date_from": options["date_to"],
                "period_length": options["period_length"],
                "result_selection": options["result_selection"],
                "journal_ids": [(6, 0, self._selected_journal_ids(options))],
            })
        if report_key == "journal_audit":
            vals.update({
                "journal_ids": [(6, 0, self._selected_journal_ids(options))],
                "sort_selection": options["sort_selection"],
                "amount_currency": options["amount_currency"],
            })
        if report_key in ("bank_book", "cash_book", "day_book"):
            config = self.DIRECT_REPORTS[report_key]
            journals = self._journal_ids_for_type(options, config.get("journal_type"))
            vals["journal_ids"] = [(6, 0, journals)]
            if report_key in ("bank_book", "cash_book"):
                default_account_ids = self.env["account.journal"].browse(journals).mapped("default_account_id").ids
                vals.update({
                    "account_ids": [(6, 0, default_account_ids)],
                    "display_account": options["display_account"],
                    "sortby": options["sortby"],
                    "initial_balance": options["initial_balance"],
                })
        if report_key in ("trial_balance", "general_ledger", "partner_ledger"):
            vals["journal_ids"] = [(6, 0, self._selected_journal_ids(options))]
        wizard = self.env[wizard_model].create(vals)
        return wizard.with_context(
            active_model=wizard_model,
            active_id=wizard.id,
            active_ids=[wizard.id],
        ).check_report()
