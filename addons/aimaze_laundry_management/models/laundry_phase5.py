from odoo import api, fields, models


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

    phase5_invoice_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_payment_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_delivery_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_complaint_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_notification_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_wallet_count = fields.Integer(compute="_compute_phase5_smart_counts")
    phase5_subscription_count = fields.Integer(compute="_compute_phase5_smart_counts")

    def _compute_phase5_smart_counts(self):
        Wallet = self.env["aimaze.customer.wallet"].sudo()
        Subscription = self.env["aimaze.laundry.subscription"].sudo()
        Notification = self.env["aimaze.notification.queue"].sudo()
        for order in self:
            order.phase5_invoice_count = 1 if order.invoice_id else 0
            order.phase5_payment_count = len(order.payment_ids)
            order.phase5_delivery_count = len(order.delivery_ids)
            order.phase5_complaint_count = len(order.complaint_ids)
            order.phase5_notification_count = Notification.search_count([("order_id", "=", order.id)])
            order.phase5_wallet_count = Wallet.search_count([("partner_id", "=", order.partner_id.id), ("company_id", "=", order.company_id.id)]) if order.partner_id else 0
            order.phase5_subscription_count = Subscription.search_count([("partner_id", "=", order.partner_id.id), ("company_id", "=", order.company_id.id)]) if order.partner_id else 0

    def _phase5_action(self, name, model, domain, view_mode="list,form", context=None):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain,
            "context": context or {},
        }

    def action_phase5_open_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.invoice_id.id, "view_mode": "form"}
        return self._phase5_action("Invoices", "account.move", [("laundry_order_id", "=", self.id)], "list,form")

    def action_phase5_open_payments(self):
        return self._phase5_action("Payments", "account.payment", [("aimaze_laundry_order_id", "=", self.id)])

    def action_phase5_open_deliveries(self):
        return self._phase5_action("Pickup & Delivery", "aimaze.laundry.delivery", [("order_id", "=", self.id)], "kanban,list,form")

    def action_phase5_open_complaints(self):
        return self._phase5_action("Complaints", "aimaze.laundry.complaint", [("order_id", "=", self.id)], "kanban,list,form")

    def action_phase5_open_notifications(self):
        return self._phase5_action("Notifications", "aimaze.notification.queue", [("order_id", "=", self.id)])

    def action_phase5_open_wallets(self):
        return self._phase5_action("Customer Wallet", "aimaze.customer.wallet", [("partner_id", "=", self.partner_id.id), ("company_id", "=", self.company_id.id)])

    def action_phase5_open_subscriptions(self):
        return self._phase5_action("Customer Subscriptions", "aimaze.laundry.subscription", [("partner_id", "=", self.partner_id.id), ("company_id", "=", self.company_id.id)])


class ResPartner(models.Model):
    _inherit = "res.partner"

    phase5_laundry_order_count = fields.Integer(compute="_compute_phase5_laundry_counts")
    phase5_laundry_revenue = fields.Monetary(compute="_compute_phase5_laundry_counts", currency_field="currency_id")
    phase5_wallet_count = fields.Integer(compute="_compute_phase5_laundry_counts")
    phase5_subscription_count = fields.Integer(compute="_compute_phase5_laundry_counts")
    phase5_complaint_count = fields.Integer(compute="_compute_phase5_laundry_counts")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)

    def _compute_phase5_laundry_counts(self):
        Order = self.env["aimaze.laundry.order"].sudo()
        Wallet = self.env["aimaze.customer.wallet"].sudo()
        Subscription = self.env["aimaze.laundry.subscription"].sudo()
        Complaint = self.env["aimaze.laundry.complaint"].sudo()
        for partner in self:
            commercial = partner.commercial_partner_id
            orders = Order.search([("partner_id.commercial_partner_id", "=", commercial.id)])
            partner.phase5_laundry_order_count = len(orders)
            partner.phase5_laundry_revenue = sum(orders.mapped("amount_total"))
            partner.phase5_wallet_count = Wallet.search_count([("partner_id.commercial_partner_id", "=", commercial.id)])
            partner.phase5_subscription_count = Subscription.search_count([("partner_id.commercial_partner_id", "=", commercial.id)])
            partner.phase5_complaint_count = Complaint.search_count([("partner_id.commercial_partner_id", "=", commercial.id)])

    def action_phase5_open_laundry_orders(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Laundry Orders", "res_model": "aimaze.laundry.order", "view_mode": "list,kanban,form", "domain": [("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id)]}

    def action_phase5_open_laundry_wallets(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Wallets", "res_model": "aimaze.customer.wallet", "view_mode": "list,form", "domain": [("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id)]}

    def action_phase5_open_laundry_subscriptions(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Subscriptions", "res_model": "aimaze.laundry.subscription", "view_mode": "list,form", "domain": [("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id)]}

    def action_phase5_open_laundry_complaints(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Complaints", "res_model": "aimaze.laundry.complaint", "view_mode": "kanban,list,form", "domain": [("partner_id.commercial_partner_id", "=", self.commercial_partner_id.id)]}


class LaundryBranch(models.Model):
    _inherit = "aimaze.laundry.branch"

    phase5_order_count = fields.Integer(compute="_compute_phase5_branch_counts")
    phase5_revenue = fields.Monetary(compute="_compute_phase5_branch_counts", currency_field="currency_id")
    phase5_delivery_count = fields.Integer(compute="_compute_phase5_branch_counts")
    phase5_driver_count = fields.Integer(compute="_compute_phase5_branch_counts")

    def _compute_phase5_branch_counts(self):
        Order = self.env["aimaze.laundry.order"].sudo()
        Delivery = self.env["aimaze.laundry.delivery"].sudo()
        for branch in self:
            orders = Order.search([("branch_id", "=", branch.id), ("state", "not in", ("cancelled", "draft"))])
            deliveries = Delivery.search([("branch_id", "=", branch.id)])
            branch.phase5_order_count = len(orders)
            branch.phase5_revenue = sum(orders.mapped("amount_total"))
            branch.phase5_delivery_count = len(deliveries)
            branch.phase5_driver_count = len(deliveries.mapped("driver_id"))

    def action_phase5_open_branch_orders(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Branch Orders", "res_model": "aimaze.laundry.order", "view_mode": "list,kanban,form", "domain": [("branch_id", "=", self.id)]}

    def action_phase5_open_branch_deliveries(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Branch Deliveries", "res_model": "aimaze.laundry.delivery", "view_mode": "kanban,list,form", "domain": [("branch_id", "=", self.id)]}
