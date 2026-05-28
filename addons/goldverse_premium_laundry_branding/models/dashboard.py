from datetime import datetime, time

from odoo import _, fields, models


class LaundryExecutiveDashboard(models.TransientModel):
    _inherit = "aimaze.laundry.executive.dashboard"

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
                order_base_domain + [("state", "in", ("ready", "ready_for_delivery"))],
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
        return self.action_open_orders()
