from collections import defaultdict
from datetime import datetime, time, timedelta
from html import escape

from odoo import _, api, fields, models


class LaundryExecutiveDashboard(models.TransientModel):
    _inherit = "aimaze.laundry.executive.dashboard"
    _transient_max_hours = 0

    gv_customer_type_filter = fields.Selection(
        [("all", "All Customers"), ("b2c", "B2C"), ("b2b", "B2B")],
        string="Customer Type",
        default="all",
    )
    gv_service_type_id = fields.Many2one("aimaze.laundry.service", string="Service Type")
    goldverse_command_center_html = fields.Html(
        string="GoldVerse Executive Command Center",
        compute="_compute_goldverse_command_center_html",
        sanitize=False,
    )
    goldverse_company_warning = fields.Char(compute="_compute_goldverse_command_center_html")
    gv_total_sales = fields.Monetary(string="Total Sales", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_cash_sales = fields.Monetary(string="Cash Sales", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_bank_sales = fields.Monetary(string="Bank Sales", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_ibft_sales = fields.Monetary(string="IBFT Sales", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_credit_sales = fields.Monetary(string="Credit Sales", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_total_orders = fields.Integer(string="Total Orders", compute="_compute_goldverse_dashboard_cards")
    gv_draft_orders = fields.Integer(string="Draft", compute="_compute_goldverse_dashboard_cards")
    gv_sent_warehouse_orders = fields.Integer(string="Sent to Warehouse", compute="_compute_goldverse_dashboard_cards")
    gv_received_warehouse_orders = fields.Integer(string="Received from Warehouse", compute="_compute_goldverse_dashboard_cards")
    gv_delivered_customer_orders = fields.Integer(string="Delivered to Customers", compute="_compute_goldverse_dashboard_cards")
    gv_gross_profit = fields.Monetary(string="Gross Profit", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_total_expenses = fields.Monetary(string="Total Exp", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_net_profit = fields.Monetary(string="Net Profit", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_top_expenses = fields.Monetary(string="Top 5 Expenses", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_receivables = fields.Monetary(string="Receivables", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_advances_payables = fields.Monetary(string="Advances Payables", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_cash_sales_share_label = fields.Char(string="Cash Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_bank_sales_share_label = fields.Char(string="Bank Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_ibft_sales_share_label = fields.Char(string="IBFT Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_credit_sales_share_label = fields.Char(string="Credit Sales Share", compute="_compute_goldverse_dashboard_cards")

    def _goldverse_base_order_domain(self):
        self.ensure_one()
        domain = [("company_id", "=", self.company_id.id)]
        if self.branch_id:
            domain.append(("branch_id", "=", self.branch_id.id))
        return domain

    def _goldverse_period_datetimes(self, today_only=False):
        self.ensure_one()
        today = fields.Date.context_today(self)
        date_from = today if today_only else (self.date_from or today)
        date_to = today if today_only else (self.date_to or date_from)
        return (
            fields.Datetime.to_string(datetime.combine(date_from, time.min)),
            fields.Datetime.to_string(datetime.combine(date_to, time.max)),
        )

    def _goldverse_period_order_domain(self, today_only=False):
        date_from, date_to = self._goldverse_period_datetimes(today_only=today_only)
        return self._goldverse_base_order_domain() + [
            ("order_date", ">=", date_from),
            ("order_date", "<=", date_to),
        ]

    def _goldverse_action(self, name, model, domain, view_mode="list,form", context=None):
        views = [(False, mode.strip()) for mode in view_mode.split(",") if mode.strip()]
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "views": views,
            "domain": domain,
            "context": context or {},
            "target": "current",
        }

    @api.model
    def _goldverse_find_company(self):
        company = self.env["res.company"].sudo().search([("name", "ilike", "GoldVerse")], limit=1)
        if not company:
            company = self.env["res.company"].sudo().search([("name", "ilike", "Gold Verse")], limit=1)
        return company or self.env.company

    @api.model
    def action_goldverse_open_executive_dashboard(self):
        company = self._goldverse_find_company()
        today = fields.Date.context_today(self)
        dashboard_menu = self.env.ref(
            "aimaze_laundry_management.menu_laundry_executive_dashboard",
            raise_if_not_found=False,
        )
        dashboard = self.create(
            {
                "company_id": company.id,
                "period_filter": "today",
                "date_from": today,
                "date_to": today,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Executive Dashboard"),
            "res_model": "aimaze.laundry.executive.dashboard",
            "view_mode": "form",
            "res_id": dashboard.id,
            "target": "current",
            "context": {
                "allowed_company_ids": self.env.context.get("allowed_company_ids", [company.id]),
            },
            "params": {
                "menu_id": dashboard_menu.id if dashboard_menu else False,
            },
        }

    @api.model
    def goldverse_ensure_dashboard_record(self, forced_id=7):
        """Keep old dashboard URLs from failing when browser history has a stale id."""
        if self.browse(forced_id).exists():
            return True
        company = self.env["res.company"].sudo().search([("name", "=", "GoldVerse Premium (Pvt.) Limited")], limit=1) or self.env.company
        today = fields.Date.context_today(self)
        self.env.cr.execute(
            """
            INSERT INTO aimaze_laundry_executive_dashboard
                (id, create_uid, create_date, write_uid, write_date, name, company_id, period_filter, date_from, date_to)
            VALUES
                (%s, %s, NOW(), %s, NOW(), %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                forced_id,
                self.env.uid,
                self.env.uid,
                _("Executive Dashboard"),
                company.id,
                "today",
                today,
                today,
            ),
        )
        self.env.cr.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('aimaze_laundry_executive_dashboard', 'id'),
                GREATEST((SELECT COALESCE(MAX(id), 0) FROM aimaze_laundry_executive_dashboard), %s)
            )
            """,
            (forced_id,),
        )
        return True

    @api.model
    def goldverse_apply_today_dashboard_defaults(self):
        today = fields.Date.context_today(self)
        dashboards = self.sudo().search([])
        if dashboards:
            dashboards.write(
                {
                    "period_filter": "today",
                    "date_from": today,
                    "date_to": today,
                }
            )
        return True

    def _goldverse_order_ids_for_period(self):
        Order = self.env["aimaze.laundry.order"]
        return Order.search(self._goldverse_period_order_domain() + [("state", "not in", ("draft", "cancelled"))]).ids

    def action_goldverse_open_dashboard_card(self):
        self.ensure_one()
        card = self.env.context.get("goldverse_card")
        order_base_domain = self._goldverse_base_order_domain()
        period_order_domain = self._goldverse_period_order_domain()
        order_ids = self._goldverse_order_ids_for_period()

        if card == "today_sales":
            return self._goldverse_action(
                _("Today Sales"),
                "aimaze.laundry.order",
                self._goldverse_period_order_domain(today_only=True) + [("state", "not in", ("draft", "cancelled"))],
                "list,kanban,form",
            )
        if card == "month_sales":
            return self._goldverse_action(
                _("Sales Orders"),
                "aimaze.laundry.order",
                period_order_domain + [("state", "not in", ("draft", "cancelled"))],
                "list,kanban,form",
            )
        if card == "pending_orders":
            return self._goldverse_action(
                _("Pending Orders"),
                "aimaze.laundry.order",
                order_base_domain + [("state", "not in", ("delivered", "invoiced", "paid", "cancelled"))],
                "list,kanban,form",
            )
        if card == "ready_orders":
            return self._goldverse_action(
                _("Ready Orders"),
                "aimaze.laundry.order",
                order_base_domain + [("state", "in", ("ready", "ready_for_delivery", "pending_customer_delivery"))],
                "list,kanban,form",
            )
        if card == "delivered_orders":
            return self._goldverse_action(
                _("Delivered Orders"),
                "aimaze.laundry.order",
                period_order_domain + [("state", "in", ("delivered", "invoiced", "paid"))],
                "list,kanban,form",
            )
        if card == "delayed_orders":
            return self._goldverse_action(
                _("Delayed Orders"),
                "aimaze.laundry.order",
                order_base_domain + [("is_delayed", "=", True)],
                "list,kanban,form",
            )
        if card == "open_complaints":
            domain = [("company_id", "=", self.company_id.id), ("state", "not in", ("closed", "rejected"))]
            if self.branch_id:
                domain.append(("branch_id", "=", self.branch_id.id))
            return self._goldverse_action(_("Open Complaints"), "aimaze.laundry.complaint", domain, "list,form,activity")
        if card == "rewash_ratio":
            return self._goldverse_action(
                _("Garments Rewashed"),
                "aimaze.laundry.garment",
                [("order_id", "in", order_ids), ("rewash_count", ">", 0)],
                "list,form",
            )
        if card == "wallet_liability":
            domain = [("company_id", "=", self.company_id.id)]
            return self._goldverse_action(_("Customer Wallets"), "aimaze.customer.wallet", domain, "list,form")
        if card == "advance_liability":
            return self._goldverse_action(
                _("Advance Liability"),
                "account.payment",
                [("laundry_is_advance", "=", True), ("company_id", "=", self.company_id.id)],
                "list,form,pivot,graph",
            )
        if card == "receivables":
            return self._goldverse_action(
                _("Receivables"),
                "account.move.line",
                [
                    ("company_id", "=", self.company_id.id),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("amount_residual", "!=", 0),
                ],
                "list,pivot,graph",
            )
        if card == "branch_profit":
            domain = [("company_id", "=", self.company_id.id)]
            if self.branch_id:
                domain.append(("branch_id", "=", self.branch_id.id))
            return self._goldverse_action(_("Branch Profitability"), "aimaze.laundry.branch.profitability", domain, "graph,pivot,list,form")
        if card == "staff_score":
            return self._goldverse_action(_("Staff Tasks & Productivity"), "aimaze.laundry.staff.task", [("order_id", "in", order_ids)], "list,form,pivot,graph")
        if card == "driver_performance":
            return self._goldverse_action(_("Driver Performance"), "aimaze.laundry.delivery", [("order_id", "in", order_ids)], "kanban,list,form")
        if card == "machine_utilization":
            domain = [("company_id", "=", self.company_id.id)]
            if self.branch_id:
                domain.append(("branch_id", "=", self.branch_id.id))
            return self._goldverse_action(_("Machines"), "aimaze.laundry.machine", domain, "list,form,activity")
        if card == "low_stock":
            return self._goldverse_action(
                _("Low Stock Items"),
                "product.product",
                [("qty_available", "<", 5), ("type", "in", ("consu", "product"))],
                "list,form",
            )
        if card == "gv_total_sales":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Total Sales"), "account.move", self._gv_invoice_domain(date_from, date_to), "list,form,pivot,graph")
        if card == "gv_cash_sales":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Cash Sales"), "account.payment", self._gv_payment_bucket_domain(date_from, date_to, "cash"), "list,form,pivot,graph")
        if card == "gv_bank_sales":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Bank Sales"), "account.payment", self._gv_payment_bucket_domain(date_from, date_to, "bank"), "list,form,pivot,graph")
        if card == "gv_ibft_sales":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("IBFT Sales"), "account.payment", self._gv_payment_bucket_domain(date_from, date_to, "ibft"), "list,form,pivot,graph")
        if card == "gv_credit_sales":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Credit Sales"), "account.move", self._gv_invoice_domain(date_from, date_to) + [("amount_residual", ">", 0)], "list,form,pivot,graph")
        if card == "gv_total_orders":
            return self._goldverse_action(_("Total Orders"), "aimaze.laundry.order", period_order_domain + [("state", "!=", "cancelled")], "list,kanban,form,pivot,graph")
        if card == "gv_draft_orders":
            return self._goldverse_action(_("Draft Orders"), "aimaze.laundry.order", period_order_domain + [("state", "=", "draft")], "list,kanban,form")
        if card == "gv_sent_warehouse_orders":
            return self._goldverse_action(_("Sent to Warehouse"), "aimaze.laundry.order", period_order_domain + [("warehouse_collected_datetime", "!=", False)], "list,kanban,form")
        if card == "gv_received_warehouse_orders":
            return self._goldverse_action(_("Received from Warehouse"), "aimaze.laundry.order", period_order_domain + [("warehouse_received_datetime", "!=", False)], "list,kanban,form")
        if card == "gv_delivered_customer_orders":
            return self._goldverse_action(_("Delivered to Customers"), "aimaze.laundry.order", period_order_domain + ["|", ("goldverse_actual_delivery_datetime", "!=", False), ("state", "in", ("delivered", "paid"))], "list,kanban,form")
        if card == "gv_gross_profit":
            return self._goldverse_action(_("Gross Profit Journal Items"), "account.move.line", self._goldverse_profit_domain(include_operating=False), "list,pivot,graph")
        if card == "gv_total_expenses":
            return self._goldverse_action(_("Total Expenses"), "account.move.line", self._goldverse_total_expense_domain(), "list,pivot,graph")
        if card == "gv_net_profit":
            return self._goldverse_action(_("Net Profit Journal Items"), "account.move.line", self._goldverse_profit_domain(include_operating=True), "list,pivot,graph")
        if card == "gv_top_expenses":
            return self._goldverse_action(_("Top 5 Expenses"), "account.move.line", self._goldverse_top_expense_domain(), "list,pivot,graph")
        if card == "gv_receivables":
            return self._goldverse_action(_("Receivables"), "account.move.line", self._goldverse_receivable_domain(), "list,pivot,graph")
        if card == "gv_advances_payables":
            return self._goldverse_action(_("Advances Payables"), "account.move.line", self._goldverse_advance_payable_domain(), "list,pivot,graph")
        if card == "gv_total_revenue":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Total Revenue"), "account.move", self._gv_invoice_domain(date_from, date_to), "list,form,pivot,graph")
        if card == "gv_active_customers":
            date_from, date_to = self._gv_period_date_bounds()
            invoices = self._gv_posted_invoices(date_from, date_to)
            orders = self.env["aimaze.laundry.order"].sudo().search(self._gv_order_domain(date_from, date_to))
            partner_ids = set(invoices.mapped("partner_id.commercial_partner_id").ids)
            partner_ids.update(orders.mapped("partner_id.commercial_partner_id").ids)
            return self._goldverse_action(_("Active Customers"), "res.partner", [("id", "in", list(partner_ids))], "list,form")
        if card == "gv_cash_bank_collections":
            date_from, date_to = self._gv_period_date_bounds()
            return self._goldverse_action(_("Cash & Bank Collections"), "account.payment", self._gv_payment_domain(date_from, date_to), "list,form,pivot,graph")
        return self.action_open_orders()

    def _goldverse_period_dates(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.period_filter == "yesterday":
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        return self.date_from or today, self.date_to or self.date_from or today

    def _goldverse_payment_domain(self, bucket=False):
        self.ensure_one()
        date_from, date_to = self._goldverse_period_dates()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("paid", "posted", "in_process")),
            ("payment_type", "=", "inbound"),
            ("aimaze_laundry_order_id", "!=", False),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if self.branch_id:
            domain.append(("aimaze_laundry_order_id.branch_id", "=", self.branch_id.id))
        if bucket == "cash":
            domain.extend(["|", ("journal_id.type", "=", "cash"), ("journal_id.name", "ilike", "cash")])
        elif bucket == "ibft":
            domain.extend(["|", ("journal_id.name", "ilike", "IBFT"), ("journal_id.code", "ilike", "IBFT")])
        elif bucket == "bank":
            domain.extend(
                [
                    ("journal_id.type", "=", "bank"),
                    ("journal_id.name", "not ilike", "IBFT"),
                    ("journal_id.code", "not ilike", "IBFT"),
                ]
            )
        return domain

    def _goldverse_payment_bucket(self, payment):
        journal_name = (payment.journal_id.name or "").lower()
        journal_code = (payment.journal_id.code or "").lower()
        if payment.journal_id.type == "cash" or "cash" in journal_name:
            return "cash"
        if "ibft" in journal_name or "ibft" in journal_code:
            return "ibft"
        if payment.journal_id.type == "bank":
            return "bank"
        return False

    def _goldverse_sales_method_breakdown(self, orders):
        self.ensure_one()
        totals = {"cash": 0.0, "bank": 0.0, "ibft": 0.0}
        remaining_by_order = {order.id: max(order.amount_total or 0.0, 0.0) for order in orders}
        if not remaining_by_order:
            return totals

        payments = self.env["account.payment"].sudo().search(
            self._goldverse_payment_domain(False) + [("aimaze_laundry_order_id", "in", list(remaining_by_order))],
            order="date, id",
        )
        for payment in payments:
            bucket = self._goldverse_payment_bucket(payment)
            if bucket not in totals:
                continue
            order_id = payment.aimaze_laundry_order_id.id
            remaining = max(remaining_by_order.get(order_id, 0.0), 0.0)
            amount = min(payment.amount or 0.0, remaining)
            if amount <= 0.0:
                continue
            totals[bucket] += amount
            remaining_by_order[order_id] = remaining - amount
        return totals

    def _goldverse_move_line_period_domain(self):
        self.ensure_one()
        date_from, date_to = self._goldverse_period_dates()
        return [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]

    def _goldverse_receivable_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_receivable"),
            ("amount_residual", "!=", 0),
        ]
        return domain

    def _goldverse_advance_payable_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            "|",
            ("account_id.code", "=", "413004"),
            ("account_id.name", "ilike", "Other Payable"),
        ]
        return domain

    def _goldverse_profit_domain(self, include_operating=True):
        self.ensure_one()
        account_types = ("income", "income_other", "expense_direct_cost")
        if include_operating:
            account_types += ("expense", "expense_depreciation")
        return self._goldverse_move_line_period_domain() + [("account_id.account_type", "in", account_types)]

    def _goldverse_top_expense_domain(self):
        self.ensure_one()
        base_domain = self._goldverse_total_expense_domain()
        account_ids = [row["account_id"] for row in self._gv_top_expense_rows(*self._gv_period_date_bounds()) if row.get("account_id")]
        return base_domain + [("account_id", "in", account_ids or [0])]

    def _goldverse_total_expense_domain(self):
        self.ensure_one()
        return self._goldverse_move_line_period_domain() + [
            ("account_id.account_type", "in", ("expense", "expense_depreciation", "expense_direct_cost")),
        ]

    def _gv_top_expense_total(self, date_from, date_to):
        return sum(row["value"] for row in self._gv_top_expense_rows(date_from, date_to))

    def _gv_total_expense_value(self, date_from, date_to):
        profit = self._gv_profit_values(date_from, date_to)
        return (profit.get("direct_cost") or 0.0) + (profit.get("operating_expense") or 0.0)

    def _gv_top_expense_rows(self, date_from, date_to):
        self.ensure_one()
        MoveLine = self.env["account.move.line"].sudo()
        base_domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("account_id.account_type", "in", ("expense", "expense_depreciation", "expense_direct_cost")),
        ]
        grouped = MoveLine.read_group(base_domain, ["balance:sum"], ["account_id"], orderby="balance desc", limit=5)
        rows = []
        for group in grouped:
            account = group.get("account_id")
            if not account:
                continue
            rows.append(
                {
                    "account_id": account[0],
                    "name": account[1],
                    "value": group.get("balance_sum", 0.0),
                }
            )
        return rows

    def action_goldverse_refresh_dashboard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("GoldVerse Executive Command Center"),
            "res_model": "aimaze.laundry.executive.dashboard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def action_goldverse_export_pdf_placeholder(self):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export PDF"),
                "message": _("Executive dashboard PDF export placeholder is ready for the next report-export wiring step."),
                "type": "info",
                "sticky": False,
            },
        }

    def _gv_money(self, value):
        self.ensure_one()
        currency = self.company_id.currency_id or self.env.company.currency_id
        symbol = currency.symbol or currency.name or ""
        return "%s%s" % (format(value or 0.0, ",.2f"), (" " + symbol) if symbol else "")

    def _gv_number(self, value):
        return format(value or 0, ",.0f")

    def _gv_percent(self, value):
        return "%+.1f%%" % (value or 0.0)

    def _gv_trend(self, current, previous):
        current = current or 0.0
        previous = previous or 0.0
        if abs(previous) < 0.0001:
            return 100.0 if current else 0.0
        return ((current - previous) / abs(previous)) * 100.0

    def _gv_period_date_bounds(self):
        self.ensure_one()
        date_from, date_to = self._goldverse_period_dates()
        if date_to < date_from:
            date_to = date_from
        return date_from, date_to

    def _gv_previous_period(self, date_from, date_to):
        days = max((date_to - date_from).days, 0)
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days)
        return previous_from, previous_to

    def _gv_datetime_domain(self, field_name, date_from, date_to):
        return [
            (field_name, ">=", fields.Datetime.to_string(datetime.combine(date_from, time.min))),
            (field_name, "<=", fields.Datetime.to_string(datetime.combine(date_to, time.max))),
        ]

    def _gv_customer_domain(self):
        self.ensure_one()
        if self.gv_customer_type_filter and self.gv_customer_type_filter != "all":
            return [("customer_type", "=", self.gv_customer_type_filter)]
        return []

    def _gv_partner_customer_domain(self):
        self.ensure_one()
        if self.gv_customer_type_filter and self.gv_customer_type_filter != "all":
            return [("partner_id.goldverse_customer_category", "=", self.gv_customer_type_filter)]
        return []

    def _gv_order_domain(self, date_from, date_to, include_cancelled=False):
        self.ensure_one()
        domain = [("company_id", "=", self.company_id.id)] + self._gv_datetime_domain("order_date", date_from, date_to)
        if self.branch_id:
            domain.append(("branch_id", "=", self.branch_id.id))
        if not include_cancelled:
            domain.append(("state", "!=", "cancelled"))
        domain += self._gv_customer_domain()
        if self.gv_service_type_id:
            domain.append(("line_ids.service_id", "=", self.gv_service_type_id.id))
        return domain

    def _gv_invoice_domain(self, date_from, date_to):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ] + self._gv_partner_customer_domain()
        if self.branch_id and "laundry_branch_id" in self.env["account.move"]._fields:
            domain.append(("laundry_branch_id", "=", self.branch_id.id))
        if self.gv_service_type_id and self.gv_service_type_id.product_id:
            domain.append(("invoice_line_ids.product_id", "=", self.gv_service_type_id.product_id.id))
        return domain

    def _gv_posted_invoices(self, date_from, date_to):
        return self.env["account.move"].sudo().search(self._gv_invoice_domain(date_from, date_to))

    def _gv_invoice_revenue(self, invoices):
        income_lines = invoices.mapped("line_ids").filtered(
            lambda line: line.parent_state == "posted"
            and line.account_id.account_type in ("income", "income_other")
        )
        return -sum(income_lines.mapped("balance"))

    def _gv_profit_values(self, date_from, date_to):
        MoveLine = self.env["account.move.line"].sudo()
        lines = MoveLine.search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("account_id.account_type", "in", ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")),
            ]
        )
        revenue = -sum(lines.filtered(lambda line: line.account_id.account_type in ("income", "income_other")).mapped("balance"))
        direct_cost = sum(
            lines.filtered(
                lambda line: line.account_id.account_type == "expense_direct_cost"
                or (line.account_id.code or "").startswith("61")
            ).mapped("balance")
        )
        operating_expense = sum(
            lines.filtered(
                lambda line: line.account_id.account_type in ("expense", "expense_depreciation")
                and not (line.account_id.code or "").startswith("61")
            ).mapped("balance")
        )
        gross_profit = revenue - direct_cost
        net_profit = gross_profit - operating_expense
        return {
            "revenue": revenue,
            "direct_cost": direct_cost,
            "operating_expense": operating_expense,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "gp_percent": (gross_profit / revenue * 100.0) if revenue else 0.0,
            "np_percent": (net_profit / revenue * 100.0) if revenue else 0.0,
        }

    def _gv_payment_domain(self, date_from, date_to):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("payment_type", "=", "inbound"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ]
        if "state" in self.env["account.payment"]._fields:
            domain.append(("state", "in", ("paid", "posted", "in_process")))
        return domain

    def _gv_payment_bucket_domain(self, date_from, date_to, bucket):
        domain = self._gv_payment_domain(date_from, date_to)
        if bucket == "cash":
            domain += ["|", ("journal_id.type", "=", "cash"), ("journal_id.name", "ilike", "cash")]
        elif bucket == "ibft":
            domain += ["|", ("journal_id.name", "ilike", "IBFT"), ("journal_id.code", "ilike", "IBFT")]
        elif bucket == "bank":
            domain += [
                ("journal_id.type", "=", "bank"),
                ("journal_id.name", "not ilike", "IBFT"),
                ("journal_id.code", "not ilike", "IBFT"),
            ]
        return domain

    def _gv_collection_breakdown(self, date_from, date_to):
        payments = self.env["account.payment"].sudo().search(self._gv_payment_domain(date_from, date_to))
        totals = defaultdict(float)
        for payment in payments:
            journal_name = (payment.journal_id.name or "").lower()
            journal_code = (payment.journal_id.code or "").lower()
            if payment.journal_id.type == "cash" or "cash" in journal_name:
                bucket = "Cash Collection"
            elif "ibft" in journal_name or "ibft" in journal_code:
                bucket = "IBFT Collection"
            elif payment.journal_id.type == "bank":
                bucket = "Bank Collection"
            else:
                bucket = payment.journal_id.display_name or _("Other Collection")
            totals[bucket] += payment.amount or 0.0
        return dict(totals)

    def _gv_order_lines(self, date_from, date_to):
        OrderLine = self.env["aimaze.laundry.order.line"].sudo()
        domain = [("order_id", "in", self.env["aimaze.laundry.order"].sudo().search(self._gv_order_domain(date_from, date_to)).ids)]
        if self.gv_service_type_id:
            domain.append(("service_id", "=", self.gv_service_type_id.id))
        return OrderLine.search(domain)

    def _gv_line_amount(self, line):
        return line.price_subtotal or line.goldverse_total_amount or ((line.quantity or 0.0) * (line.unit_price or 0.0))

    def _gv_group_order_lines(self, lines, key_getter):
        grouped = defaultdict(float)
        for line in lines:
            label = key_getter(line)
            if not label:
                continue
            grouped[label] += self._gv_line_amount(line)
        return sorted(grouped.items(), key=lambda item: item[1], reverse=True)

    def _gv_group_invoice_income_lines(self, invoices, key_getter):
        grouped = defaultdict(float)
        income_lines = invoices.mapped("line_ids").filtered(
            lambda line: line.parent_state == "posted"
            and line.account_id.account_type in ("income", "income_other")
        )
        for line in income_lines:
            label = key_getter(line)
            if not label:
                continue
            grouped[label] += -line.balance
        return sorted(grouped.items(), key=lambda item: item[1], reverse=True)

    def _gv_service_label_from_order_line(self, line):
        service_name = (line.service_id.display_name or "").strip()
        category_name = ((line.goldverse_category_id or line.service_id.category_id).display_name or "").strip()
        subcategory_name = ((line.goldverse_subcategory_id or line.service_id.goldverse_subcategory_id).display_name or "").strip()
        parts = [part for part in (category_name, subcategory_name, service_name) if part]
        return " / ".join(parts)

    def _gv_service_label_from_invoice_line(self, line):
        service_name = ((line.product_id.display_name if line.product_id else "") or line.name or "").strip()
        category_name = ""
        subcategory_name = ""
        if line.product_id and hasattr(line.product_id, "goldverse_subcategory_id"):
            subcategory_name = (line.product_id.goldverse_subcategory_id.display_name or "").strip()
        if line.product_id and line.product_id.categ_id:
            category_name = (line.product_id.categ_id.display_name or "").strip()
        parts = [part for part in (category_name, subcategory_name, service_name) if part]
        return " / ".join(parts)

    def _gv_month_starts(self, date_from, date_to):
        cursor = date_from.replace(day=1)
        while cursor <= date_to:
            yield cursor
            next_month = cursor.month + 1
            next_year = cursor.year + (1 if next_month > 12 else 0)
            next_month = 1 if next_month > 12 else next_month
            cursor = cursor.replace(year=next_year, month=next_month, day=1)

    def _gv_month_label(self, value):
        return value.strftime("%b %Y")

    def _gv_month_end(self, value):
        next_month = value.month + 1
        next_year = value.year + (1 if next_month > 12 else 0)
        next_month = 1 if next_month > 12 else next_month
        return value.replace(year=next_year, month=next_month, day=1) - timedelta(days=1)

    def _gv_monthly_profit_trend(self, date_from, date_to):
        rows = []
        for month_start in self._gv_month_starts(date_from, date_to):
            month_end = min(self._gv_month_end(month_start), date_to)
            month_start = max(month_start, date_from)
            profit = self._gv_profit_values(month_start, month_end)
            rows.append(
                {
                    "label": self._gv_month_label(month_start),
                    "revenue": profit["revenue"],
                    "gross_profit": profit["gross_profit"],
                    "net_profit": profit["net_profit"],
                    "gp_percent": profit["gp_percent"],
                    "np_percent": profit["np_percent"],
                }
            )
        return rows

    def _gv_receivable_lines(self):
        return self.env["account.move.line"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("parent_state", "=", "posted"),
                ("account_id.account_type", "=", "asset_receivable"),
                ("amount_residual", "!=", 0),
            ]
        )

    def _gv_receivable_aging(self, date_to):
        buckets = {"0-30 Days": 0.0, "31-60 Days": 0.0, "61-90 Days": 0.0, "90+ Days": 0.0}
        for line in self._gv_receivable_lines().filtered(lambda item: item.amount_residual > 0):
            due_date = line.date_maturity or line.date or date_to
            age = max((date_to - due_date).days, 0)
            if age <= 30:
                buckets["0-30 Days"] += line.amount_residual
            elif age <= 60:
                buckets["31-60 Days"] += line.amount_residual
            elif age <= 90:
                buckets["61-90 Days"] += line.amount_residual
            else:
                buckets["90+ Days"] += line.amount_residual
        return buckets

    def _gv_receivable_total(self):
        return sum(self._gv_receivable_lines().filtered(lambda line: line.amount_residual > 0).mapped("amount_residual"))

    def _gv_customer_analytics(self, date_from, date_to):
        invoices = self._gv_posted_invoices(date_from, date_to)
        revenue_by_partner = defaultdict(float)
        invoice_count_by_partner = defaultdict(int)
        for move in invoices:
            partner = move.partner_id.commercial_partner_id or move.partner_id
            revenue_by_partner[partner] += self._gv_invoice_revenue(move)
            invoice_count_by_partner[partner] += 1
        receivable_by_partner = defaultdict(float)
        for line in self._gv_receivable_lines().filtered(lambda item: item.amount_residual > 0):
            partner = line.partner_id.commercial_partner_id or line.partner_id
            receivable_by_partner[partner] += line.amount_residual
        top_rows = []
        for partner, revenue in sorted(revenue_by_partner.items(), key=lambda item: item[1], reverse=True)[:10]:
            top_rows.append(
                {
                    "name": partner.display_name,
                    "orders": invoice_count_by_partner[partner],
                    "revenue": revenue,
                    "outstanding": receivable_by_partner[partner],
                }
            )
        active_customers = len(revenue_by_partner)
        first_invoice_domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
        ] + self._gv_partner_customer_domain()
        new_customers = 0
        for partner in revenue_by_partner:
            first_invoice = self.env["account.move"].sudo().search(
                first_invoice_domain + [("partner_id.commercial_partner_id", "=", partner.id)],
                order="invoice_date asc, id asc",
                limit=1,
            )
            if first_invoice and first_invoice.invoice_date and date_from <= first_invoice.invoice_date <= date_to:
                new_customers += 1
        repeat_customers = len([partner for partner, count in invoice_count_by_partner.items() if count > 1])
        revenue_total = sum(revenue_by_partner.values())
        return {
            "top_rows": top_rows,
            "active": active_customers,
            "new": new_customers,
            "repeat": repeat_customers,
            "retention": (repeat_customers / active_customers * 100.0) if active_customers else 0.0,
            "avg_spend": (revenue_total / active_customers) if active_customers else 0.0,
        }

    def _gv_advance_values(self, date_from, date_to):
        Payment = self.env["account.payment"].sudo()
        domain = self._gv_payment_domain(date_from, date_to)
        if "laundry_is_advance" in Payment._fields or "goldverse_wallet_receipt_id" in Payment._fields:
            advance_domain = list(domain)
            if "laundry_is_advance" in Payment._fields and "goldverse_wallet_receipt_id" in Payment._fields:
                advance_domain += ["|", ("laundry_is_advance", "=", True), ("goldverse_wallet_receipt_id", "!=", False)]
            elif "laundry_is_advance" in Payment._fields:
                advance_domain.append(("laundry_is_advance", "=", True))
            else:
                advance_domain.append(("goldverse_wallet_receipt_id", "!=", False))
            advance_received = sum(Payment.search(advance_domain).mapped("amount"))
        else:
            advance_received = 0.0
        credit_lines = self._gv_receivable_lines().filtered(lambda line: line.amount_residual < 0)
        advance_balance = abs(sum(credit_lines.mapped("amount_residual")))
        return {
            "received": advance_received,
            "utilized": max(advance_received - advance_balance, 0.0),
            "balance": advance_balance,
        }

    def _gv_complaint_count(self):
        if "aimaze.laundry.complaint" not in self.env.registry:
            return 0
        domain = [("company_id", "=", self.company_id.id), ("state", "not in", ("closed", "rejected"))]
        if self.branch_id:
            domain.append(("branch_id", "=", self.branch_id.id))
        return self.env["aimaze.laundry.complaint"].sudo().search_count(domain)

    def _gv_empty_state(self):
        return (
            '<div class="gv-empty o_goldverse_empty_state">'
            '<div class="empty-icon"><i class="fa fa-bar-chart"></i></div>'
            '<div class="empty-title">No data available</div>'
            '<div class="empty-text">No records found for the selected period.</div>'
            '</div>'
        )

    def _gv_bar_chart(self, rows, label="Revenue"):
        if not rows:
            return self._gv_empty_state()
        total = sum(value for _, value in rows) or 1.0
        max_value = max(value for _, value in rows) or 1.0
        rendered = []
        for name, value in rows[:5]:
            width = max(4.0, (value / max_value) * 100.0)
            share = (value / total) * 100.0
            rendered.append(
                '<div class="gv-bar-row" title="%s: %s"><div class="gv-bar-label">%s</div>'
                '<div class="gv-bar-track"><span style="width: %.2f%%"></span></div>'
                '<div class="gv-bar-value">%s <em>%.1f%%</em></div></div>'
                % (
                    escape(str(name)),
                    escape(self._gv_money(value)),
                    escape(str(name)),
                    width,
                    escape(self._gv_money(value)),
                    share,
                )
            )
        return "".join(rendered)

    def _gv_line_chart(self, rows, series):
        if not rows or not any(any(row.get(key) for key, _label, _color in series) for row in rows):
            return self._gv_empty_state()
        width, height, padding = 640, 260, 32
        values = [row.get(key, 0.0) for row in rows for key, _label, _color in series]
        max_value = max(values) if values else 0.0
        min_value = min(0.0, min(values) if values else 0.0)
        scale = max(max_value - min_value, 1.0)
        point_count = max(len(rows) - 1, 1)
        polylines = []
        for key, label, color in series:
            points = []
            for index, row in enumerate(rows):
                x = padding + (index / point_count) * (width - padding * 2)
                y = height - padding - (((row.get(key, 0.0) - min_value) / scale) * (height - padding * 2))
                points.append("%.2f,%.2f" % (x, y))
            polylines.append(
                '<polyline fill="none" stroke="%s" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" points="%s"/>'
                % (color, " ".join(points))
            )
        labels = "".join(
            '<span><i style="background:%s"></i>%s</span>' % (color, escape(label))
            for _key, label, color in series
        )
        month_labels = "".join(
            '<text x="%.2f" y="%s" text-anchor="middle">%s</text>'
            % (padding + (index / point_count) * (width - padding * 2), height - 7, escape(row["label"].split()[0]))
            for index, row in enumerate(rows)
        )
        return (
            '<div class="gv-chart-legend">%s</div><svg class="gv-line-chart" viewBox="0 0 %s %s" role="img">'
            '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#dbeafe"/>%s%s</svg>'
        ) % (labels, width, height, padding, height - padding, width - padding, height - padding, "".join(polylines), month_labels)

    def _gv_donut_chart(self, rows):
        rows = [(name, value) for name, value in rows if value]
        if not rows:
            return self._gv_empty_state()
        colors = ["#06b6d4", "#10b981", "#c9a227", "#f59e0b", "#8b5cf6", "#ef4444"]
        total = sum(value for _, value in rows) or 1.0
        cursor = 0.0
        stops = []
        legend = []
        for index, (name, value) in enumerate(rows[:6]):
            pct = (value / total) * 100.0
            color = colors[index % len(colors)]
            stops.append("%s %.2f%% %.2f%%" % (color, cursor, cursor + pct))
            cursor += pct
            legend.append(
                '<div><i style="background:%s"></i><span>%s</span><strong>%s</strong><em>%.1f%%</em></div>'
                % (color, escape(str(name)), escape(self._gv_money(value)), pct)
            )
        return (
            '<div class="gv-donut-wrap"><div class="gv-donut" style="background: conic-gradient(%s);">'
            '<span>%s</span></div><div class="gv-donut-legend">%s</div></div>'
        ) % (", ".join(stops), escape(self._gv_money(total)), "".join(legend))

    def _gv_click_attrs(self, card_key):
        if not card_key:
            return ""
        return ' role="button" tabindex="0" data-gv-dashboard-card="%s"' % escape(card_key)

    def _gv_kpi_card(self, title, value, previous, icon, accent, is_money=True, card_key=False):
        trend = self._gv_trend(value, previous)
        trend_class = "up" if trend >= 0 else "down"
        formatted_value = self._gv_money(value) if is_money else self._gv_number(value)
        comparison = self._gv_money(previous) if is_money else self._gv_number(previous)
        return (
            '<div class="gv-kpi-card o_goldverse_kpi_card gv-clickable-card" style="--gv-accent:%s"%s><div class="gv-kpi-icon"><i class="fa %s"></i></div>'
            '<span class="o_goldverse_kpi_label">%s</span><strong class="o_goldverse_kpi_value">%s</strong><em class="o_goldverse_kpi_trend %s">%s vs previous</em><small>Previous: %s</small></div>'
        ) % (
            accent,
            self._gv_click_attrs(card_key),
            icon,
            escape(title),
            escape(formatted_value),
            trend_class,
            escape(self._gv_percent(trend)),
            escape(comparison),
        )

    def _gv_sales_card(self, title, value, card_key, accent, share=False, icon="fa-line-chart"):
        share_html = ""
        if share is not False:
            share_html = '<em class="o_goldverse_kpi_trend">%s share</em>' % escape("%.1f%%" % share)
        return (
            '<div class="gv-sales-card o_goldverse_kpi_card gv-clickable-card" style="--gv-accent:%s"%s>'
            '<div class="gv-kpi-icon"><i class="fa %s"></i></div>'
            '<div class="gv-card-copy"><span class="o_goldverse_kpi_label">%s</span><strong class="o_goldverse_kpi_value">%s</strong>%s</div></div>'
        ) % (
            accent,
            self._gv_click_attrs(card_key),
            icon,
            escape(title),
            escape(self._gv_money(value)),
            share_html,
        )

    def _gv_small_card(self, title, value, accent="#06b6d4", money=True):
        formatted = self._gv_money(value) if money else (("%.1f%%" % value) if isinstance(value, float) else self._gv_number(value))
        return '<div class="gv-mini-card o_goldverse_kpi_card" style="--gv-accent:%s"><span class="o_goldverse_kpi_label">%s</span><strong class="o_goldverse_kpi_value">%s</strong></div>' % (
            accent,
            escape(title),
            escape(formatted),
        )

    def _gv_customer_table(self, rows):
        if not rows:
            return self._gv_empty_state()
        body = []
        for row in rows[:10]:
            body.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (
                    escape(row["name"]),
                    escape(self._gv_number(row["orders"])),
                    escape(self._gv_money(row["revenue"])),
                    escape(self._gv_money(row["outstanding"])),
                )
            )
        return (
            '<table class="gv-customer-table o_goldverse_table"><thead><tr><th>Customer Name</th><th>Orders</th><th>Revenue</th><th>Outstanding Balance</th></tr></thead>'
            '<tbody>%s</tbody></table>'
        ) % "".join(body)

    def _gv_alerts(self, data):
        alert_specs = [
            (
                "critical" if data["receivable_over_60"] else "positive",
                "Receivables > 60 Days",
                self._gv_money(data["receivable_over_60"]),
                "Older receivables require management follow-up." if data["receivable_over_60"] else "No old receivable pressure in the current view.",
            ),
            (
                "warning" if data["major_customer"]["amount"] else "info",
                "Major Customer Outstanding",
                self._gv_money(data["major_customer"]["amount"]),
                data["major_customer"]["name"] or "No major customer outstanding balance found.",
            ),
            (
                "critical" if data["revenue_declining"] else "positive",
                "Declining Revenue",
                self._gv_percent(data["revenue_trend"]),
                "Revenue is below the previous comparable period." if data["revenue_declining"] else "Revenue is stable or improving versus previous period.",
            ),
            (
                "warning" if data["gp_declining"] else "positive",
                "Declining Gross Profit %",
                "%.1f%%" % data["profit"]["gp_percent"],
                "Gross profit margin is weaker than the previous period." if data["gp_declining"] else "Gross profit margin is stable or improving.",
            ),
            (
                "positive" if data["collections_total"] else "info",
                "Collections Target Achieved",
                self._gv_money(data["collections_total"]),
                "Collections recorded in the selected period." if data["collections_total"] else "No collections found for the selected period.",
            ),
            (
                "positive" if data["customers"]["new"] else "info",
                "Customer Growth Positive",
                self._gv_number(data["customers"]["new"]),
                "New customers detected in the selected period." if data["customers"]["new"] else "No new customers detected in the selected period.",
            ),
            (
                "warning" if data["complaints_pending"] else "positive",
                "Complaints Pending",
                self._gv_number(data["complaints_pending"]),
                "Open complaints need review." if data["complaints_pending"] else "No open complaints found.",
            ),
        ]
        return "".join(
            '<div class="gv-alert o_goldverse_alert %s"><i class="alert-dot"></i><div><span class="o_goldverse_alert_title">%s</span><strong class="o_goldverse_alert_value">%s</strong><p class="o_goldverse_alert_text">%s</p></div></div>'
            % (severity, escape(title), escape(value), escape(message))
            for severity, title, value, message in alert_specs
        )

    def _gv_command_data(self):
        self.ensure_one()
        date_from, date_to = self._gv_period_date_bounds()
        previous_from, previous_to = self._gv_previous_period(date_from, date_to)
        invoices = self._gv_posted_invoices(date_from, date_to)
        previous_invoices = self._gv_posted_invoices(previous_from, previous_to)
        profit = self._gv_profit_values(date_from, date_to)
        previous_profit = self._gv_profit_values(previous_from, previous_to)
        revenue = profit["revenue"]
        previous_revenue = previous_profit["revenue"]
        orders = self.env["aimaze.laundry.order"].sudo().search(self._gv_order_domain(date_from, date_to))
        previous_orders = self.env["aimaze.laundry.order"].sudo().search(self._gv_order_domain(previous_from, previous_to))
        order_lines = self._gv_order_lines(date_from, date_to)
        top_services = self._gv_group_order_lines(order_lines, self._gv_service_label_from_order_line)
        top_categories = self._gv_group_order_lines(order_lines, lambda line: (line.goldverse_category_id or line.service_id.category_id).display_name)
        top_subcategories = self._gv_group_order_lines(
            order_lines,
            lambda line: (line.goldverse_subcategory_id or line.service_id.goldverse_subcategory_id).display_name,
        )
        service_composition = self._gv_group_order_lines(order_lines, self._gv_service_label_from_order_line)
        if not top_services:
            top_services = self._gv_group_invoice_income_lines(invoices, self._gv_service_label_from_invoice_line)
        if not top_categories:
            top_categories = self._gv_group_invoice_income_lines(
                invoices,
                lambda line: (line.product_id.categ_id.display_name if line.product_id and line.product_id.categ_id else ""),
            )
        if not service_composition:
            service_composition = top_services
        collections = self._gv_collection_breakdown(date_from, date_to)
        receivable_aging = self._gv_receivable_aging(date_to)
        customers = self._gv_customer_analytics(date_from, date_to)
        advances = self._gv_advance_values(date_from, date_to)
        monthly = self._gv_monthly_profit_trend(date_from, date_to)
        cost_breakdown = []
        if profit["direct_cost"]:
            cost_breakdown.append(("Direct Cost", profit["direct_cost"]))
        if profit["operating_expense"]:
            cost_breakdown.append(("Operating Expenses", profit["operating_expense"]))
        if profit["gross_profit"]:
            cost_breakdown.append(("Gross Profit", profit["gross_profit"]))
        receivable_rows = customers["top_rows"]
        major_customer = max(receivable_rows, key=lambda row: row["outstanding"], default={"name": "", "outstanding": 0.0})
        collections_total = sum(collections.values())
        revenue_trend = self._gv_trend(revenue, previous_revenue)
        order_count = len(orders) or len(invoices)
        previous_order_count = len(previous_orders) or len(previous_invoices)
        total_expenses = self._gv_total_expense_value(date_from, date_to)
        previous_total_expenses = self._gv_total_expense_value(previous_from, previous_to)
        top_expenses = self._gv_top_expense_total(date_from, date_to)
        previous_top_expenses = self._gv_top_expense_total(previous_from, previous_to)
        top_expense_rows = self._gv_top_expense_rows(date_from, date_to)
        return {
            "date_from": date_from,
            "date_to": date_to,
            "previous_from": previous_from,
            "previous_to": previous_to,
            "revenue": revenue,
            "previous_revenue": previous_revenue,
            "profit": profit,
            "previous_profit": previous_profit,
            "orders": order_count,
            "previous_orders": previous_order_count,
            "average_order_value": (revenue / order_count) if order_count else 0.0,
            "previous_aov": (previous_revenue / previous_order_count) if previous_order_count else 0.0,
            "total_expenses": total_expenses,
            "previous_total_expenses": previous_total_expenses,
            "customers": customers,
            "receivables": self._gv_receivable_total(),
            "collections": collections,
            "collections_total": collections_total,
            "top_services": top_services,
            "top_categories": top_categories,
            "top_subcategories": top_subcategories,
            "service_composition": service_composition,
            "monthly": monthly,
            "receivable_aging": receivable_aging,
            "advances": advances,
            "top_expenses": top_expenses,
            "previous_top_expenses": previous_top_expenses,
            "top_expense_rows": top_expense_rows,
            "cost_breakdown": cost_breakdown,
            "receivable_over_60": receivable_aging["61-90 Days"] + receivable_aging["90+ Days"],
            "major_customer": {"name": major_customer.get("name") or "", "amount": major_customer.get("outstanding") or 0.0},
            "revenue_trend": revenue_trend,
            "revenue_declining": revenue_trend < 0,
            "gp_declining": profit["gp_percent"] < previous_profit["gp_percent"],
            "complaints_pending": self._gv_complaint_count(),
        }

    @api.depends("company_id", "branch_id", "date_from", "date_to", "period_filter", "gv_customer_type_filter", "gv_service_type_id")
    def _compute_goldverse_command_center_html(self):
        for dashboard in self:
            company = dashboard._goldverse_find_company()
            warning = ""
            if not company or "gold" not in (company.name or "").lower():
                company = dashboard.company_id or dashboard.env.company
                warning = _("GoldVerse company not found. Showing current company data.")
            if dashboard.company_id != company:
                dashboard.company_id = company
            dashboard.goldverse_company_warning = warning
            data = dashboard._gv_command_data()
            sales_total = data["revenue"] or 0.0
            collections = data["collections"]
            remaining_sales = sales_total
            cash_sales = min(collections.get("Cash Collection", 0.0), remaining_sales)
            remaining_sales -= cash_sales
            bank_sales = min(collections.get("Bank Collection", 0.0), remaining_sales)
            remaining_sales -= bank_sales
            ibft_sales = min(collections.get("IBFT Collection", 0.0), remaining_sales)
            remaining_sales -= ibft_sales
            credit_sales = max(remaining_sales, 0.0)
            sales_share = lambda amount: ((amount or 0.0) / sales_total * 100.0) if sales_total else 0.0
            range_label = dashboard.date_range_label or "%s - %s" % (data["date_from"], data["date_to"])
            current_dt = fields.Datetime.context_timestamp(dashboard, fields.Datetime.now()) or datetime.now()
            greeting = _("Good morning") if current_dt.hour < 12 else (_("Good afternoon") if current_dt.hour < 17 else _("Good evening"))
            customer_filter_label = dict(dashboard._fields["gv_customer_type_filter"].selection).get(
                dashboard.gv_customer_type_filter,
                _("All Customers"),
            )
            service_filter_label = dashboard.gv_service_type_id.display_name or _("All Services")
            branch_label = dashboard.branch_id.display_name or _("All Branches")
            top_service_name = data["top_services"][0][0] if data["top_services"] else _("No service trend yet")
            top_service_value = data["top_services"][0][1] if data["top_services"] else 0.0
            collection_ratio = ((data["collections_total"] or 0.0) / sales_total * 100.0) if sales_total else 0.0
            receivable_ratio = ((data["receivables"] or 0.0) / sales_total * 100.0) if sales_total else 0.0

            def _render_points(items, empty_text):
                clean_items = [item for item in items if item]
                if not clean_items:
                    clean_items = [empty_text]
                return "".join("<li>%s</li>" % escape(item) for item in clean_items)

            summary_points = [
                _("Revenue %s across %s orders for the selected period.")
                % (dashboard._gv_money(data["revenue"]), dashboard._gv_number(data["orders"])),
                _("Gross profit %s with margin %.1f%% and average order value %s.")
                % (
                    dashboard._gv_money(data["profit"]["gross_profit"]),
                    data["profit"]["gp_percent"],
                    dashboard._gv_money(data["average_order_value"]),
                ),
                _("Collections stand at %s while receivables are %s.")
                % (dashboard._gv_money(data["collections_total"]), dashboard._gv_money(data["receivables"])),
            ]
            risk_points = []
            if data["receivable_over_60"]:
                risk_points.append(
                    _("Receivables older than 60 days are %s.")
                    % dashboard._gv_money(data["receivable_over_60"])
                )
            if data["major_customer"]["amount"]:
                risk_points.append(
                    _("%s is the largest outstanding customer at %s.")
                    % (
                        data["major_customer"]["name"] or _("A major customer"),
                        dashboard._gv_money(data["major_customer"]["amount"]),
                    )
                )
            if data["revenue_declining"]:
                risk_points.append(_("Revenue is trailing the previous comparison period by %s.") % dashboard._gv_percent(abs(data["revenue_trend"])))
            if data["complaints_pending"]:
                risk_points.append(_("%s complaint records are still open.") % dashboard._gv_number(data["complaints_pending"]))
            focus_points = [
                _("Top earning service is %s at %s.") % (top_service_name, dashboard._gv_money(top_service_value)) if top_service_value else "",
                _("Credit exposure currently represents %.1f%% of recognized sales.") % sales_share(credit_sales) if sales_total else "",
                _("Collections conversion is %.1f%% and open AR is %.1f%% of revenue.") % (collection_ratio, receivable_ratio) if sales_total else "",
                _("Highest expense head is %s.") % data["top_expense_rows"][0]["name"] if data["top_expense_rows"] else "",
            ]
            quick_tags = "".join(
                '<span class="gv-brief-tag">%s</span>'
                % escape(tag)
                for tag in [
                    company.name or _("GoldVerse"),
                    branch_label,
                    dashboard.currency_id.name or "PKR",
                ]
            )
            sales_cards = [
                dashboard._gv_sales_card("Total Sales", sales_total, "gv_total_sales", "#c9a227", icon="fa-shopping-cart"),
                dashboard._gv_sales_card("Cash Sales", cash_sales, "gv_cash_sales", "#10b981", sales_share(cash_sales), "fa-money"),
                dashboard._gv_sales_card("Bank Sales", bank_sales, "gv_bank_sales", "#0ea5e9", sales_share(bank_sales), "fa-bank"),
                dashboard._gv_sales_card("IBFT Sales", ibft_sales, "gv_ibft_sales", "#8b5cf6", sales_share(ibft_sales), "fa-exchange"),
                dashboard._gv_sales_card("Credit Sales", credit_sales, "gv_credit_sales", "#f59e0b", sales_share(credit_sales), "fa-credit-card"),
            ]
            kpis = [
                dashboard._gv_kpi_card("Total Revenue", data["revenue"], data["previous_revenue"], "fa-line-chart", "#c9a227", card_key="gv_total_revenue"),
                dashboard._gv_kpi_card("Gross Profit", data["profit"]["gross_profit"], data["previous_profit"]["gross_profit"], "fa-trophy", "#10b981", card_key="gv_gross_profit"),
                dashboard._gv_kpi_card("Total Exp", data["total_expenses"], data["previous_total_expenses"], "fa-arrow-circle-down", "#fb923c", card_key="gv_total_expenses"),
                dashboard._gv_kpi_card("Net Profit", data["profit"]["net_profit"], data["previous_profit"]["net_profit"], "fa-pie-chart", "#06b6d4", card_key="gv_net_profit"),
                dashboard._gv_kpi_card("Total Orders", data["orders"], data["previous_orders"], "fa-shopping-bag", "#8b5cf6", is_money=False, card_key="gv_total_orders"),
                dashboard._gv_kpi_card("Average Order Value", data["average_order_value"], data["previous_aov"], "fa-calculator", "#f59e0b", card_key="gv_total_orders"),
                dashboard._gv_kpi_card("Active Customers", data["customers"]["active"], 0, "fa-users", "#0ea5e9", is_money=False, card_key="gv_active_customers"),
                dashboard._gv_kpi_card("Receivables", data["receivables"], 0, "fa-credit-card", "#ef4444", card_key="gv_receivables"),
                dashboard._gv_kpi_card("Cash & Bank Collections", data["collections_total"], 0, "fa-bank", "#14b8a6", card_key="gv_cash_bank_collections"),
            ]
            customer_cards = [
                dashboard._gv_small_card("New Customers", data["customers"]["new"], "#06b6d4", money=False),
                dashboard._gv_small_card("Repeat Customers", data["customers"]["repeat"], "#10b981", money=False),
                dashboard._gv_small_card("Customer Retention", data["customers"]["retention"], "#c9a227", money=False),
                dashboard._gv_small_card("Average Customer Spend", data["customers"]["avg_spend"], "#8b5cf6"),
            ]
            advance_cards = [
                dashboard._gv_small_card("Advance Received", data["advances"]["received"], "#10b981"),
                dashboard._gv_small_card("Advance Utilized", data["advances"]["utilized"], "#f59e0b"),
                dashboard._gv_small_card("Advance Balance", data["advances"]["balance"], "#8b5cf6"),
            ]
            collection_cards = [
                dashboard._gv_small_card(name, value, "#06b6d4")
                for name, value in sorted(data["collections"].items())
            ] or [dashboard._gv_empty_state()]
            warning_html = '<div class="gv-warning">%s</div>' % escape(warning) if warning else ""
            dashboard.goldverse_command_center_html = f"""
                <div class="gv-command-center gv-command-center-luxe">
                    <section class="gv-brief-shell">
                        <aside class="gv-greeting-card">
                            <span class="gv-brief-kicker">{escape(greeting)}</span>
                            <h1>GoldVerse Executive Analytics</h1>
                            <strong>{escape(dashboard.env.user.name or "Administrator")}</strong>
                            <p>{escape(range_label)}</p>
                            <div class="gv-brief-tags">{quick_tags}</div>
                        </aside>
                        <section class="gv-morning-brief">
                            <div class="gv-brief-head">
                                <span class="gv-brief-kicker">Executive management brief</span>
                                <span class="gv-brief-meta">Customer filter: {escape(customer_filter_label)} | Service filter: {escape(service_filter_label)}</span>
                            </div>
                            <div class="gv-brief-grid">
                                <div class="gv-brief-column">
                                    <h3>Performance snapshot</h3>
                                    <ul>{_render_points(summary_points, _("No performance summary is available yet."))}</ul>
                                </div>
                                <div class="gv-brief-column">
                                    <h3>Risks</h3>
                                    <ul>{_render_points(risk_points, _("No critical risk indicators are currently active."))}</ul>
                                </div>
                                <div class="gv-brief-column">
                                    <h3>Focus actions</h3>
                                    <ul>{_render_points(focus_points, _("Monitor revenue, collections, and cost movement through the day."))}</ul>
                                </div>
                            </div>
                        </section>
                    </section>
                    {warning_html}
                    <section class="gv-panel gv-sales-panel o_goldverse_section">
                        <div class="gv-panel-head o_goldverse_section_header"><h2>Sales command view</h2><span class="section-tag">{escape(range_label)}</span></div>
                        <div class="gv-sales-grid o_goldverse_kpi_grid">{"".join(sales_cards)}</div>
                    </section>
                    <section class="gv-panel gv-kpi-panel o_goldverse_section">
                        <div class="gv-panel-head o_goldverse_section_header"><h2>Executive KPI summary</h2><span class="section-tag">Revenue, profit, orders, customers</span></div>
                        <div class="gv-kpi-grid o_goldverse_kpi_grid">{"".join(kpis)}</div>
                    </section>
                    <div class="gv-section-band"><span>Revenue intelligence</span></div>
                    <section class="gv-dashboard-row gv-row-70-30 o_goldverse_chart_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card">
                            <div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Monthly Revenue vs Gross Profit</h2><span class="section-tag o_goldverse_chart_subtitle">{escape(range_label)}</span></div>
                            {dashboard._gv_line_chart(data["monthly"], [("revenue", "Revenue", "#d97706"), ("gross_profit", "Gross Profit", "#059669")])}
                        </div>
                        <div class="gv-panel gv-revenue-composition-panel o_goldverse_section o_goldverse_chart_card">
                            <div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Revenue Composition</h2><span class="section-tag o_goldverse_chart_subtitle">Actual services</span></div>
                            {dashboard._gv_donut_chart(data["service_composition"][:6])}
                        </div>
                    </section>
                    <div class="gv-section-band"><span>Business mix</span></div>
                    <section class="gv-dashboard-row gv-row-3 o_goldverse_three_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Top Service Revenue</h2><span class="section-tag o_goldverse_chart_subtitle">Top 5</span></div>{dashboard._gv_bar_chart(data["top_services"], "Revenue")}</div>
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Top Category Revenue</h2><span class="section-tag o_goldverse_chart_subtitle">Top 5</span></div>{dashboard._gv_bar_chart(data["top_categories"], "Revenue")}</div>
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Top Sub Category Revenue</h2><span class="section-tag o_goldverse_chart_subtitle">Top 5</span></div>{dashboard._gv_bar_chart(data["top_subcategories"], "Revenue")}</div>
                    </section>
                    <div class="gv-section-band"><span>Customer and working capital</span></div>
                    <section class="gv-dashboard-row gv-row-60-40 o_goldverse_two_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card">
                            <div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Top Customers by Revenue</h2><span class="section-tag o_goldverse_chart_subtitle">Top 10</span></div>
                            {dashboard._gv_bar_chart([(row["name"], row["revenue"]) for row in data["customers"]["top_rows"]], "Revenue")}
                            {dashboard._gv_customer_table(data["customers"]["top_rows"])}
                        </div>
                        <div class="gv-panel o_goldverse_section">
                            <div class="gv-panel-head o_goldverse_section_header"><h2>Customer intelligence</h2><span class="section-tag">Period quality</span></div>
                            <div class="gv-mini-grid">{"".join(customer_cards)}</div>
                        </div>
                    </section>
                    <section class="gv-dashboard-row gv-row-3 o_goldverse_three_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Receivable Aging</h2><span class="section-tag o_goldverse_chart_subtitle">Open AR</span></div>{dashboard._gv_donut_chart(list(data["receivable_aging"].items()))}</div>
                        <div class="gv-panel o_goldverse_section"><div class="gv-panel-head o_goldverse_section_header"><h2>Collections</h2><span class="section-tag">Payment journals</span></div><div class="gv-mini-grid">{"".join(collection_cards)}</div></div>
                        <div class="gv-panel o_goldverse_section"><div class="gv-panel-head o_goldverse_section_header"><h2>Customer advances</h2><span class="section-tag">AR credit balance</span></div><div class="gv-mini-grid">{"".join(advance_cards)}</div></div>
                    </section>
                    <div class="gv-section-band"><span>Profitability and control</span></div>
                    <section class="gv-dashboard-row gv-row-3 o_goldverse_three_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Revenue vs Cost Breakdown</h2><span class="section-tag o_goldverse_chart_subtitle">Actual accounts</span></div>{dashboard._gv_donut_chart(data["cost_breakdown"])}</div>
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Gross Profit % Trend</h2><span class="section-tag o_goldverse_chart_subtitle">Monthly</span></div>{dashboard._gv_line_chart(data["monthly"], [("gp_percent", "Gross Profit %", "#059669")])}</div>
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card"><div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Net Profit % Trend</h2><span class="section-tag o_goldverse_chart_subtitle">Monthly</span></div>{dashboard._gv_line_chart(data["monthly"], [("np_percent", "Net Profit %", "#7c3aed")])}</div>
                    </section>
                    <section class="gv-dashboard-row gv-row-60-40 o_goldverse_two_grid">
                        <div class="gv-panel o_goldverse_section o_goldverse_chart_card">
                            <div class="gv-panel-head o_goldverse_section_header"><h2 class="o_goldverse_chart_title">Top 5 Expenses</h2><span class="section-tag o_goldverse_chart_subtitle">Expense heads</span></div>
                            {dashboard._gv_bar_chart([(row["name"], row["value"]) for row in data["top_expense_rows"]], "Expense")}
                        </div>
                        <div class="gv-panel gv-alert-center o_goldverse_section">
                            <div class="gv-panel-head o_goldverse_section_header"><h2>Executive alerts center</h2><span class="section-tag">Live management signals</span></div>
                            <div class="gv-alert-grid o_goldverse_alert_grid">{dashboard._gv_alerts(data)}</div>
                        </div>
                    </section>
                </div>
            """

    @api.depends("company_id", "branch_id", "date_from", "date_to")
    def _compute_goldverse_dashboard_cards(self):
        Order = self.env["aimaze.laundry.order"].sudo()
        MoveLine = self.env["account.move.line"].sudo()
        for dashboard in self:
            order_domain = dashboard._goldverse_base_order_domain()
            period_order_domain = dashboard._goldverse_period_order_domain()
            period_orders = Order.search(period_order_domain + [("state", "!=", "cancelled")])
            active_period_orders = period_orders.filtered(lambda order: order.state != "draft")

            dashboard.gv_total_sales = sum(active_period_orders.mapped("amount_total"))
            sales_breakdown = dashboard._goldverse_sales_method_breakdown(active_period_orders)
            dashboard.gv_cash_sales = sales_breakdown["cash"]
            dashboard.gv_bank_sales = sales_breakdown["bank"]
            dashboard.gv_ibft_sales = sales_breakdown["ibft"]
            dashboard.gv_credit_sales = max(
                dashboard.gv_total_sales - dashboard.gv_cash_sales - dashboard.gv_bank_sales - dashboard.gv_ibft_sales,
                0.0,
            )

            dashboard.gv_total_orders = len(period_orders)
            dashboard.gv_draft_orders = len(period_orders.filtered(lambda order: order.state == "draft"))
            dashboard.gv_sent_warehouse_orders = Order.search_count(period_order_domain + [("warehouse_collected_datetime", "!=", False)])
            dashboard.gv_received_warehouse_orders = Order.search_count(period_order_domain + [("warehouse_received_datetime", "!=", False)])
            dashboard.gv_delivered_customer_orders = Order.search_count(
                period_order_domain + ["|", ("goldverse_actual_delivery_datetime", "!=", False), ("state", "in", ("delivered", "paid"))]
            )

            profit_lines = MoveLine.search(dashboard._goldverse_profit_domain(include_operating=True))
            revenue = -sum(profit_lines.filtered(lambda line: line.account_id.account_type in ("income", "income_other")).mapped("balance"))
            direct_cost = sum(profit_lines.filtered(lambda line: line.account_id.account_type == "expense_direct_cost").mapped("balance"))
            operating_expense = sum(profit_lines.filtered(lambda line: line.account_id.account_type in ("expense", "expense_depreciation")).mapped("balance"))
            dashboard.gv_gross_profit = revenue - direct_cost
            dashboard.gv_total_expenses = direct_cost + operating_expense
            dashboard.gv_net_profit = revenue - direct_cost - operating_expense

            top_expense_lines = MoveLine.search(dashboard._goldverse_top_expense_domain())
            dashboard.gv_top_expenses = sum(top_expense_lines.mapped("balance"))
            dashboard.gv_receivables = sum(MoveLine.search(dashboard._goldverse_receivable_domain()).mapped("amount_residual"))
            dashboard.gv_advances_payables = abs(sum(MoveLine.search(dashboard._goldverse_advance_payable_domain()).mapped("balance")))
            sales_total = dashboard.gv_total_sales or 0.0
            dashboard.gv_cash_sales_share_label = "%.1f%%" % ((dashboard.gv_cash_sales / sales_total) * 100) if sales_total else "0.0%"
            dashboard.gv_bank_sales_share_label = "%.1f%%" % ((dashboard.gv_bank_sales / sales_total) * 100) if sales_total else "0.0%"
            dashboard.gv_ibft_sales_share_label = "%.1f%%" % ((dashboard.gv_ibft_sales / sales_total) * 100) if sales_total else "0.0%"
            dashboard.gv_credit_sales_share_label = "%.1f%%" % ((dashboard.gv_credit_sales / sales_total) * 100) if sales_total else "0.0%"
