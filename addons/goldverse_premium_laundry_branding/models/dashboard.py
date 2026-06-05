from datetime import datetime, time

from odoo import _, api, fields, models


class LaundryExecutiveDashboard(models.TransientModel):
    _inherit = "aimaze.laundry.executive.dashboard"
    _transient_max_hours = 0

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
    gv_net_profit = fields.Monetary(string="Net Profit", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_top_expenses = fields.Monetary(string="Top 5 Expenses", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_receivables = fields.Monetary(string="Receivables", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_advances_payables = fields.Monetary(string="Advances Payables", compute="_compute_goldverse_dashboard_cards", currency_field="currency_id")
    gv_cash_sales_share_label = fields.Char(string="Cash Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_bank_sales_share_label = fields.Char(string="Bank Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_ibft_sales_share_label = fields.Char(string="IBFT Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_credit_sales_share_label = fields.Char(string="Credit Sales Share", compute="_compute_goldverse_dashboard_cards")
    gv_gross_profit_margin_label = fields.Char(string="Gross Profit Margin", compute="_compute_goldverse_dashboard_cards")

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
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain,
            "context": context or {},
            "target": "current",
        }

    @api.model
    def action_goldverse_open_executive_dashboard(self):
        company = self.env.company
        dashboard = self.create({"company_id": company.id})
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
                "ytd",
                fields.Date.start_of(today, "year"),
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
            return self._goldverse_action(_("Total Sales"), "aimaze.laundry.order", period_order_domain + [("state", "not in", ("cancelled",))], "list,kanban,form,pivot,graph")
        if card == "gv_cash_sales":
            return self._goldverse_action(_("Cash Sales"), "account.payment", self._goldverse_payment_domain("cash"), "list,form,pivot,graph")
        if card == "gv_bank_sales":
            return self._goldverse_action(_("Bank Sales"), "account.payment", self._goldverse_payment_domain("bank"), "list,form,pivot,graph")
        if card == "gv_ibft_sales":
            return self._goldverse_action(_("IBFT Sales"), "account.payment", self._goldverse_payment_domain("ibft"), "list,form,pivot,graph")
        if card == "gv_credit_sales":
            return self._goldverse_action(_("Credit Sales"), "aimaze.laundry.order", period_order_domain + [("balance_amount", ">", 0), ("state", "not in", ("draft", "cancelled"))], "list,kanban,form,pivot,graph")
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
        if card == "gv_net_profit":
            return self._goldverse_action(_("Net Profit Journal Items"), "account.move.line", self._goldverse_profit_domain(include_operating=True), "list,pivot,graph")
        if card == "gv_top_expenses":
            return self._goldverse_action(_("Top 5 Expenses"), "account.move.line", self._goldverse_top_expense_domain(), "list,pivot,graph")
        if card == "gv_receivables":
            return self._goldverse_action(_("Receivables"), "account.move.line", self._goldverse_receivable_domain(), "list,pivot,graph")
        if card == "gv_advances_payables":
            return self._goldverse_action(_("Advances Payables"), "account.move.line", self._goldverse_advance_payable_domain(), "list,pivot,graph")
        return self.action_open_orders()

    def _goldverse_period_dates(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
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
        MoveLine = self.env["account.move.line"].sudo()
        base_domain = self._goldverse_move_line_period_domain() + [
            ("account_id.account_type", "in", ("expense", "expense_depreciation", "expense_direct_cost")),
        ]
        grouped = MoveLine.read_group(base_domain, ["balance:sum"], ["account_id"], orderby="balance desc", limit=5)
        account_ids = [group["account_id"][0] for group in grouped if group.get("account_id")]
        return base_domain + [("account_id", "in", account_ids or [0])]

    @api.depends("company_id", "branch_id", "date_from", "date_to")
    def _compute_goldverse_dashboard_cards(self):
        Order = self.env["aimaze.laundry.order"].sudo()
        Payment = self.env["account.payment"].sudo()
        MoveLine = self.env["account.move.line"].sudo()
        for dashboard in self:
            order_domain = dashboard._goldverse_base_order_domain()
            period_order_domain = dashboard._goldverse_period_order_domain()
            period_orders = Order.search(period_order_domain + [("state", "!=", "cancelled")])
            active_period_orders = period_orders.filtered(lambda order: order.state != "draft")

            dashboard.gv_total_sales = sum(active_period_orders.mapped("amount_total"))
            dashboard.gv_cash_sales = sum(Payment.search(dashboard._goldverse_payment_domain("cash")).mapped("amount"))
            dashboard.gv_bank_sales = sum(Payment.search(dashboard._goldverse_payment_domain("bank")).mapped("amount"))
            dashboard.gv_ibft_sales = sum(Payment.search(dashboard._goldverse_payment_domain("ibft")).mapped("amount"))
            dashboard.gv_credit_sales = sum(active_period_orders.mapped("balance_amount"))

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
            dashboard.gv_gross_profit_margin_label = "%.2f%%" % ((dashboard.gv_gross_profit / sales_total) * 100) if sales_total else "0.00%"
