from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    laundry_arabic_name = fields.Char(string="Arabic Name")
    laundry_trn = fields.Char(string="Customer VAT / TRN")


class LaundryBranch(models.Model):
    _inherit = "aimaze.laundry.branch"

    arabic_name = fields.Char(string="Arabic Branch Name")
    commercial_registration = fields.Char(string="Commercial Registration")
    tax_registration_number = fields.Char(string="Branch TRN / Tax Number")


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

    is_delayed = fields.Boolean(compute="_compute_phase3_status", store=True)
    stage_color = fields.Char(compute="_compute_phase3_status", store=True)
    portal_status = fields.Char(compute="_compute_phase3_status", store=True)
    operation_progress = fields.Float(compute="_compute_phase3_status", store=True)

    def init(self):
        for column in ("partner_id", "branch_id", "company_id", "order_date", "state", "payment_status", "barcode"):
            self.env.cr.execute(
                "CREATE INDEX IF NOT EXISTS aimaze_laundry_order_%s_idx ON %s (%s)"
                % (column, self._table, column)
            )

    @api.depends("state", "expected_delivery_datetime")
    def _compute_phase3_status(self):
        stage_order = ["draft", "confirmed", "picked_up", "received", "sorting", "washing", "drying", "ironing", "qc", "packing", "ready", "out_for_delivery", "delivered", "invoiced", "paid"]
        color_map = {
            "draft": "muted",
            "confirmed": "info",
            "ready": "warning",
            "out_for_delivery": "primary",
            "delivered": "success",
            "invoiced": "success",
            "paid": "success",
            "cancelled": "danger",
        }
        labels = dict(self._fields["state"].selection)
        now = fields.Datetime.now()
        for order in self:
            order.is_delayed = bool(order.expected_delivery_datetime and order.expected_delivery_datetime < now and order.state not in ("delivered", "invoiced", "paid", "cancelled"))
            order.stage_color = "danger" if order.is_delayed else color_map.get(order.state, "secondary")
            order.portal_status = labels.get(order.state, order.state)
            order.operation_progress = 100.0 if order.state in ("delivered", "invoiced", "paid") else (stage_order.index(order.state) / (len(stage_order) - 1) * 100.0 if order.state in stage_order else 0.0)

    def action_open_customer_wallet(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Wallet"),
            "res_model": "aimaze.customer.wallet",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.partner_id.id), ("company_id", "=", self.company_id.id)],
            "context": {"default_partner_id": self.partner_id.id, "default_company_id": self.company_id.id, "default_currency_id": self.currency_id.id},
        }

    def action_barcode_scan(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Barcode Scan"),
            "res_model": "aimaze.laundry.scan.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_barcode": self.barcode, "default_scan_target": "order"},
        }


class LaundryGarment(models.Model):
    _inherit = "aimaze.laundry.garment"

    rfid_enabled = fields.Boolean(string="RFID Enabled")
    rfid_tag_uid = fields.Char(string="RFID Tag UID", index=True)
    package_barcode = fields.Char(string="Delivery Package Barcode", index=True)
    scan_count = fields.Integer(compute="_compute_scan_count")

    def init(self):
        for column in ("name", "barcode", "customer_id", "branch_id", "company_id", "current_stage", "rfid_tag_uid", "package_barcode"):
            self.env.cr.execute(
                "CREATE INDEX IF NOT EXISTS aimaze_laundry_garment_%s_idx ON %s (%s)"
                % (column, self._table, column)
            )

    def _compute_scan_count(self):
        Scan = self.env["aimaze.laundry.barcode.scan"]
        for garment in self:
            scan_count = Scan.search_count(["|", ("line_id", "=", garment.order_line_id.id), ("barcode", "in", [garment.barcode, garment.rfid_tag_uid])])
            garment.scan_count = scan_count

    def action_print_label(self):
        return self.env.ref("aimaze_laundry_management.action_report_laundry_garment_label_phase3").report_action(self)


class LaundryDelivery(models.Model):
    _inherit = "aimaze.laundry.delivery"

    google_maps_url = fields.Char(compute="_compute_google_maps_url", string="Google Maps Link")
    customer_phone = fields.Char(related="partner_id.phone", readonly=True)
    driver_collection_state = fields.Selection([("not_collected", "Not Collected"), ("collected", "Collected"), ("submitted", "Submitted")], default="not_collected")

    def init(self):
        for column in ("order_id", "partner_id", "branch_id", "driver_id", "state", "pickup_datetime", "delivery_datetime"):
            self.env.cr.execute(
                "CREATE INDEX IF NOT EXISTS aimaze_laundry_delivery_%s_idx ON %s (%s)"
                % (column, self._table, column)
            )

    @api.depends("address")
    def _compute_google_maps_url(self):
        for delivery in self:
            delivery.google_maps_url = "https://maps.google.com/?q=%s" % delivery.address.replace(" ", "+") if delivery.address else False

    def action_confirm_pickup_mobile(self):
        self.action_picked_up()

    def action_confirm_delivery_mobile(self):
        self.action_delivered()
        if self.cash_collected:
            self.driver_collection_state = "collected"


class LaundryExecutiveDashboard(models.TransientModel):
    _inherit = "aimaze.laundry.executive.dashboard"
    _rec_name = "name"

    name = fields.Char(default=lambda self: _("Executive Dashboard"), readonly=True)
    period_filter = fields.Selection(
        [
            ("today", "Today"),
            ("mtd", "MTD"),
            ("ytd", "YTD"),
            ("custom", "Custom"),
        ],
        default="ytd",
        required=True,
        string="Period",
    )
    date_from = fields.Date(default=lambda self: fields.Date.start_of(fields.Date.context_today(self), "year"))
    date_to = fields.Date(default=lambda self: fields.Date.context_today(self))
    date_range_label = fields.Char(compute="_compute_date_range_label")
    today_sales = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    month_sales = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    pending_orders = fields.Integer(compute="_compute_kpis")
    ready_orders = fields.Integer(compute="_compute_kpis")
    delivered_orders = fields.Integer(compute="_compute_kpis")
    delayed_orders = fields.Integer(compute="_compute_kpis")
    open_complaints = fields.Integer(compute="_compute_kpis")
    rewash_ratio = fields.Float(compute="_compute_kpis")
    wallet_liability = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    advance_liability = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    outstanding_receivables = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    branch_revenue = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    branch_profitability = fields.Monetary(compute="_compute_kpis", currency_field="currency_id")
    staff_productivity = fields.Float(compute="_compute_kpis")
    driver_performance = fields.Float(compute="_compute_kpis")
    machine_utilization = fields.Float(compute="_compute_kpis")
    inventory_low_stock = fields.Integer(compute="_compute_kpis")

    def _aimaze_period_bounds(self, period):
        today = fields.Date.context_today(self)
        if period == "today":
            return today, today
        if period == "mtd":
            return fields.Date.start_of(today, "month"), today
        if period == "ytd":
            return fields.Date.start_of(today, "year"), today
        if period == "custom":
            return today, today
        return self.date_from or today, self.date_to or today

    def _aimaze_format_dashboard_date(self, value, include_year=False):
        formatted = value.strftime("%b %d, %Y" if include_year else "%b %d")
        return formatted.replace(" 0", " ")

    @api.onchange("period_filter")
    def _onchange_period_filter(self):
        for dashboard in self:
            dashboard.date_from, dashboard.date_to = dashboard._aimaze_period_bounds(dashboard.period_filter)

    @api.onchange("date_from", "date_to")
    def _onchange_custom_dates(self):
        for dashboard in self:
            if dashboard.period_filter == "custom":
                if dashboard.date_from and dashboard.date_to and dashboard.date_to < dashboard.date_from:
                    dashboard.date_to = dashboard.date_from

    @api.depends("date_from", "date_to")
    def _compute_date_range_label(self):
        for dashboard in self:
            date_from = dashboard.date_from or fields.Date.context_today(dashboard)
            date_to = dashboard.date_to or date_from
            if date_from.year == date_to.year:
                dashboard.date_range_label = "%s - %s" % (
                    dashboard._aimaze_format_dashboard_date(date_from),
                    dashboard._aimaze_format_dashboard_date(date_to, include_year=True),
                )
            else:
                dashboard.date_range_label = "%s - %s" % (
                    dashboard._aimaze_format_dashboard_date(date_from, include_year=True),
                    dashboard._aimaze_format_dashboard_date(date_to, include_year=True),
                )

    def action_apply_dashboard_range(self):
        for dashboard in self:
            dashboard.period_filter = "custom"
            if dashboard.date_from and dashboard.date_to and dashboard.date_to < dashboard.date_from:
                dashboard.date_to = dashboard.date_from
        return {
            "type": "ir.actions.act_window",
            "name": _("Executive Dashboard"),
            "res_model": "aimaze.laundry.executive.dashboard",
            "view_mode": "form",
            "res_id": self[:1].id,
            "target": "current",
        }

    @api.depends("company_id", "branch_id", "date_from", "date_to")
    def _compute_kpis(self):
        Order = self.env["aimaze.laundry.order"]
        Complaint = self.env["aimaze.laundry.complaint"]
        Garment = self.env["aimaze.laundry.garment"]
        Wallet = self.env["aimaze.customer.wallet"]
        MoveLine = self.env["account.move.line"]
        StaffTask = self.env["aimaze.laundry.staff.task"]
        Delivery = self.env["aimaze.laundry.delivery"]
        Machine = self.env["aimaze.laundry.machine"]
        Product = self.env["product.product"]
        Profit = self.env["aimaze.laundry.branch.profitability"]
        today = fields.Date.context_today(self)
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        for dashboard in self:
            order_domain = [("company_id", "=", dashboard.company_id.id)]
            if dashboard.branch_id:
                order_domain.append(("branch_id", "=", dashboard.branch_id.id))
            date_start = datetime.combine(dashboard.date_from or today, time.min)
            date_end = datetime.combine(dashboard.date_to or today, time.max)
            period_domain = order_domain + [("order_date", ">=", date_start), ("order_date", "<=", date_end)]
            today_orders = Order.search(order_domain + [("order_date", ">=", today_start), ("order_date", "<=", today_end), ("state", "not in", ("draft", "cancelled"))])
            period_orders = Order.search(period_domain + [("state", "not in", ("draft", "cancelled"))])
            garments = Garment.search([("order_id", "in", period_orders.ids)])
            rewash = garments.filtered(lambda g: g.rewash_count > 0)
            deliveries = Delivery.search([("order_id", "in", period_orders.ids)])
            tasks = StaffTask.search([("order_id", "in", period_orders.ids)])
            machines = Machine.search([("company_id", "=", dashboard.company_id.id)] + ([("branch_id", "=", dashboard.branch_id.id)] if dashboard.branch_id else []))
            products = Product.search([("qty_available", "<", 5), ("type", "in", ("consu", "product"))])
            receivable_domain = [("company_id", "=", dashboard.company_id.id), ("account_id.account_type", "=", "asset_receivable"), ("parent_state", "=", "posted")]
            dashboard.today_sales = sum(today_orders.mapped("amount_total"))
            dashboard.month_sales = sum(period_orders.mapped("amount_total"))
            dashboard.pending_orders = Order.search_count(order_domain + [("state", "not in", ("delivered", "invoiced", "paid", "cancelled"))])
            dashboard.ready_orders = Order.search_count(order_domain + [("state", "=", "ready")])
            dashboard.delivered_orders = Order.search_count(period_domain + [("state", "in", ("delivered", "invoiced", "paid"))])
            dashboard.delayed_orders = Order.search_count(order_domain + [("is_delayed", "=", True)])
            dashboard.open_complaints = Complaint.search_count([("company_id", "=", dashboard.company_id.id), ("state", "not in", ("closed", "rejected"))])
            dashboard.rewash_ratio = (len(rewash) / len(garments) * 100.0) if garments else 0.0
            dashboard.wallet_liability = sum(Wallet.search([("company_id", "=", dashboard.company_id.id)]).mapped("balance"))
            dashboard.advance_liability = sum(period_orders.mapped("advance_paid"))
            dashboard.outstanding_receivables = sum(MoveLine.search(receivable_domain).mapped("amount_residual"))
            dashboard.branch_revenue = sum(period_orders.mapped("amount_total"))
            dashboard.branch_profitability = sum(Profit.search([("company_id", "=", dashboard.company_id.id)] + ([("branch_id", "=", dashboard.branch_id.id)] if dashboard.branch_id else [])).mapped("net_profit"))
            dashboard.staff_productivity = sum(tasks.mapped("productivity_score")) / len(tasks) if tasks else 0.0
            dashboard.driver_performance = len(deliveries.filtered(lambda d: d.state == "delivered")) / len(deliveries) * 100.0 if deliveries else 0.0
            dashboard.machine_utilization = len(machines.filtered(lambda m: m.status == "running")) / len(machines) * 100.0 if machines else 0.0
            dashboard.inventory_low_stock = len(products)


class LaundryAIAnalysis(models.Model):
    _name = "aimaze.laundry.ai.analysis"
    _description = "Laundry AI Analysis Placeholder"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    reference_type = fields.Selection(
        [
            ("stain", "Stain Analysis"),
            ("fabric", "Fabric Care Recommendation"),
            ("complaint", "Complaint Sentiment"),
            ("delay", "Delay Prediction"),
            ("revenue", "Revenue Forecast"),
            ("churn", "Customer Churn Risk"),
        ],
        required=True,
        default="stain",
    )
    order_id = fields.Many2one("aimaze.laundry.order")
    garment_id = fields.Many2one("aimaze.laundry.garment")
    partner_id = fields.Many2one("res.partner", string="Customer")
    image = fields.Binary(attachment=True)
    ai_result = fields.Text()
    confidence_score = fields.Float()
    recommendation = fields.Text()
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("reviewed", "Reviewed"), ("applied", "Applied"), ("cancelled", "Cancelled")], default="draft", tracking=True)
    notes = fields.Text()
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    branch_id = fields.Many2one("aimaze.laundry.branch")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.ai.analysis") or "New"
        return super().create(vals_list)

    def action_queue(self):
        self.write({"state": "queued"})

    def action_mark_reviewed(self):
        self.write({"state": "reviewed"})


class NotificationProvider(models.Model):
    _inherit = "aimaze.notification.provider"

    rate_limit_per_minute = fields.Integer(default=60)
    webhook_url_placeholder = fields.Char()
    last_health_check = fields.Datetime()
    health_status = fields.Selection([("unknown", "Unknown"), ("ok", "OK"), ("failed", "Failed")], default="unknown")


class LaundryAccountingReportMixin(models.AbstractModel):
    _name = "aimaze.laundry.accounting.report.mixin"
    _description = "Laundry Accounting Report Helpers"

    @api.model
    def ensure_accounting_config(self, company):
        config = self.env["aimaze.laundry.account.config"].get_config(company)
        if not config:
            raise UserError(_("Configure Laundry Accounting Configuration for %s first.") % company.display_name)
        return config
