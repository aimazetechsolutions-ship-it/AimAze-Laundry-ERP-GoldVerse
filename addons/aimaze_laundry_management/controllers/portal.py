from odoo import http
from odoo.http import request


class AimazeLaundryPortal(http.Controller):
    @http.route(["/my/laundry/orders"], type="http", auth="user", website=True)
    def portal_laundry_orders(self, **kw):
        orders = request.env["aimaze.laundry.order"].sudo().search([("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id)])
        wallets = request.env["aimaze.customer.wallet"].sudo().search([("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id)])
        subscriptions = request.env["aimaze.laundry.subscription"].sudo().search([("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id), ("state", "=", "active")])
        return request.render("aimaze_laundry_management.portal_laundry_orders", {"orders": orders, "wallets": wallets, "subscriptions": subscriptions})

    @http.route(["/my/laundry/orders/<int:order_id>"], type="http", auth="user", website=True)
    def portal_laundry_order(self, order_id, **kw):
        order = request.env["aimaze.laundry.order"].sudo().browse(order_id)
        if not order.exists() or order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return request.not_found()
        return request.render("aimaze_laundry_management.portal_laundry_order", {"order": order})

    @http.route(["/my/laundry/request-pickup"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def portal_request_pickup(self, **post):
        if request.httprequest.method == "POST":
            partner = request.env.user.partner_id.commercial_partner_id
            branch = request.env["aimaze.laundry.branch"].sudo().search([("company_id", "=", request.env.company.id)], limit=1)
            request.env["aimaze.laundry.delivery"].sudo().create(
                {
                    "job_type": "pickup",
                    "partner_id": partner.id,
                    "order_id": int(post.get("order_id")) if post.get("order_id") else request.env["aimaze.laundry.order"].sudo().create({"partner_id": partner.id, "branch_id": branch.id, "company_id": request.env.company.id}).id,
                    "branch_id": branch.id,
                    "address": post.get("address") or partner.contact_address,
                    "remarks": post.get("remarks"),
                }
            )
            return request.redirect("/my/laundry/orders")
        orders = request.env["aimaze.laundry.order"].sudo().search([("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id), ("state", "not in", ("delivered", "paid", "cancelled"))])
        return request.render("aimaze_laundry_management.portal_laundry_request_pickup", {"orders": orders})

    @http.route(["/my/laundry/complaint"], type="http", auth="user", website=True, methods=["GET", "POST"])
    def portal_submit_complaint(self, **post):
        partner = request.env.user.partner_id.commercial_partner_id
        if request.httprequest.method == "POST":
            order = request.env["aimaze.laundry.order"].sudo().browse(int(post.get("order_id"))) if post.get("order_id") else request.env["aimaze.laundry.order"].sudo()
            if order and order.partner_id.commercial_partner_id != partner:
                return request.not_found()
            request.env["aimaze.laundry.complaint"].sudo().create(
                {
                    "partner_id": partner.id,
                    "order_id": order.id if order else False,
                    "complaint_type": post.get("complaint_type") or "other",
                    "priority": "normal",
                    "notes": post.get("notes"),
                }
            )
            return request.redirect("/my/laundry/orders")
        orders = request.env["aimaze.laundry.order"].sudo().search([("partner_id", "child_of", partner.id)])
        return request.render("aimaze_laundry_management.portal_laundry_complaint", {"orders": orders})

    @http.route("/aimaze_laundry/api/orders", type="jsonrpc", auth="user")
    def api_laundry_orders(self, **kw):
        partner = request.env.user.partner_id.commercial_partner_id
        orders = request.env["aimaze.laundry.order"].search([("partner_id", "child_of", partner.id)], limit=50, order="id desc")
        return [
            {
                "id": order.id,
                "name": order.name,
                "state": order.state,
                "amount_total": order.amount_total,
                "balance_amount": order.balance_amount,
                "currency": order.currency_id.name,
            }
            for order in orders
        ]

    @http.route("/aimaze_laundry/api/customer/session", type="jsonrpc", auth="user")
    def api_customer_session(self, **kw):
        partner = request.env.user.partner_id.commercial_partner_id
        return {"authenticated": True, "partner_id": partner.id, "name": partner.display_name, "company": request.env.company.display_name}

    @http.route("/aimaze_laundry/api/driver/deliveries", type="jsonrpc", auth="user")
    def api_driver_deliveries(self, **kw):
        employee = request.env["hr.employee"].search([("user_id", "=", request.env.user.id)], limit=1)
        if not employee:
            return []
        deliveries = request.env["aimaze.laundry.delivery"].search([("driver_id", "=", employee.id), ("state", "not in", ("delivered", "cancelled"))], limit=100)
        return [
            {
                "id": delivery.id,
                "name": delivery.name,
                "job_type": delivery.job_type,
                "state": delivery.state,
                "customer": delivery.partner_id.display_name,
                "mobile": delivery.partner_id.phone,
                "address": delivery.address,
                "cash_collected": delivery.cash_collected,
            }
            for delivery in deliveries
        ]

    @http.route("/aimaze_laundry/api/staff/scan", type="jsonrpc", auth="user")
    def api_staff_scan(self, barcode=None, scan_action="open", **kw):
        wizard = request.env["aimaze.laundry.scan.wizard"].create({"barcode": barcode, "scan_action": scan_action or "open"})
        action = wizard.action_scan()
        return {"ok": True, "res_model": action.get("res_model"), "res_id": action.get("res_id")}

    @http.route("/aimaze_laundry/api/garment/<string:barcode>", type="jsonrpc", auth="user")
    def api_garment_lookup(self, barcode, **kw):
        garment = request.env["aimaze.laundry.garment"].search([("barcode", "=", barcode)], limit=1)
        if not garment:
            return {"found": False}
        return {
            "found": True,
            "id": garment.id,
            "uid": garment.name,
            "order": garment.order_id.name,
            "customer": garment.customer_id.display_name,
            "stage": garment.current_stage,
            "qc_result": garment.qc_result,
        }

    @http.route("/aimaze_laundry/api/order/status/<int:order_id>", type="jsonrpc", auth="user")
    def api_order_status(self, order_id, **kw):
        order = request.env["aimaze.laundry.order"].browse(order_id)
        if not order.exists():
            return {"found": False}
        if not request.env.user.has_group("aimaze_laundry_management.group_laundry_admin") and order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {"error": "access_denied"}
        return {"found": True, "name": order.name, "state": order.state, "portal_status": order.portal_status, "progress": order.operation_progress}

    @http.route("/aimaze_laundry/api/wallet/<int:partner_id>", type="jsonrpc", auth="user")
    def api_wallet_balance(self, partner_id, **kw):
        partner = request.env["res.partner"].browse(partner_id)
        if not partner.exists():
            return {"found": False}
        if not request.env.user.has_group("aimaze_laundry_management.group_laundry_admin") and partner.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {"error": "access_denied"}
        wallets = request.env["aimaze.customer.wallet"].search([("partner_id", "=", partner.id)])
        return {
            "found": True,
            "wallets": [{"company": wallet.company_id.display_name, "currency": wallet.currency_id.name, "balance": wallet.balance} for wallet in wallets],
        }

    @http.route("/aimaze_laundry/api/subscription/<int:partner_id>", type="jsonrpc", auth="user")
    def api_subscription_balance(self, partner_id, **kw):
        partner = request.env["res.partner"].browse(partner_id)
        if not partner.exists():
            return {"found": False}
        if not request.env.user.has_group("aimaze_laundry_management.group_laundry_admin") and partner.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {"error": "access_denied"}
        subscriptions = request.env["aimaze.laundry.subscription"].search([("partner_id", "=", partner.id), ("state", "=", "active")])
        return {
            "found": True,
            "subscriptions": [
                {
                    "name": subscription.name,
                    "package": subscription.package_id.display_name,
                    "date_end": str(subscription.date_end or ""),
                    "remaining_value": subscription.remaining_value,
                    "remaining_quantity": subscription.remaining_quantity,
                }
                for subscription in subscriptions
            ],
        }

    @http.route("/aimaze_laundry/api/complaints", type="jsonrpc", auth="user")
    def api_complaint_submit(self, order_id=False, complaint_type="other", notes=False, **kw):
        partner = request.env.user.partner_id.commercial_partner_id
        order = request.env["aimaze.laundry.order"].browse(order_id) if order_id else request.env["aimaze.laundry.order"]
        if order and order.partner_id.commercial_partner_id != partner:
            return {"error": "access_denied"}
        complaint = request.env["aimaze.laundry.complaint"].sudo().create({"partner_id": partner.id, "order_id": order.id if order else False, "complaint_type": complaint_type, "notes": notes})
        return {"ok": True, "complaint_id": complaint.id, "name": complaint.name}
