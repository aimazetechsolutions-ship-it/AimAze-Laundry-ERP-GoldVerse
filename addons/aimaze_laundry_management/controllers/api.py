import json
import time

from odoo import http
from odoo.http import request, Response


class AimazeLaundryMobileAPI(http.Controller):
    API_PREFIX = "/aimaze_laundry/mobile/v1"

    def _json_response(self, payload, status=200):
        return Response(json.dumps(payload, default=str), status=status, content_type="application/json")

    def _payload(self):
        if request.httprequest.data:
            try:
                return request.httprequest.get_json(silent=True) or {}
            except Exception:
                return {}
        return dict(request.params)

    def _success(self, data=None, meta=None, status=200):
        payload = {"success": True, "data": data or {}}
        if meta:
            payload["meta"] = meta
        return self._json_response(payload, status=status)

    def _error(self, message, status=400, code="error"):
        self._log_api("API error", level="warning", response={"message": message, "code": code}, status_code=status)
        return self._json_response({"success": False, "error": {"code": code, "message": message}}, status=status)

    def _paginate(self, model, domain, order="id desc", default_limit=50):
        params = self._payload()
        page = max(int(params.get("page") or 1), 1)
        limit = min(max(int(params.get("limit") or default_limit), 1), 100)
        offset = (page - 1) * limit
        records = request.env[model].search(domain, order=order, limit=limit, offset=offset)
        total = request.env[model].search_count(domain)
        return records, {"page": page, "limit": limit, "total": total, "has_more": offset + limit < total}

    def _partner(self):
        return request.env.user.partner_id.commercial_partner_id

    def _employee(self):
        return request.env["hr.employee"].sudo().search([("user_id", "=", request.env.user.id)], limit=1)

    def _customer_order_domain(self):
        return [("partner_id", "child_of", self._partner().id), ("company_id", "in", request.env.companies.ids)]

    def _driver_delivery_domain(self):
        employee = self._employee()
        if not employee:
            return [("id", "=", 0)]
        return [("driver_id", "=", employee.id), ("company_id", "in", request.env.companies.ids)]

    def _order_json(self, order):
        return {
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "status": order.portal_status or order.state,
            "order_date": order.order_date,
            "expected_delivery": order.expected_delivery_datetime,
            "amount_total": order.amount_total,
            "balance_amount": order.balance_amount,
            "payment_status": order.payment_status,
            "currency": order.currency_id.name,
            "branch": order.branch_id.display_name,
            "progress": order.operation_progress,
        }

    def _garment_json(self, garment):
        return {
            "id": garment.id,
            "uid": garment.name,
            "barcode": garment.barcode,
            "rfid_tag_uid": garment.rfid_tag_uid,
            "garment_type": garment.garment_type,
            "stage": garment.current_stage,
            "qc_result": garment.qc_result,
            "rewash_count": garment.rewash_count,
            "delivered": garment.delivered,
        }

    def _delivery_json(self, delivery):
        return {
            "id": delivery.id,
            "name": delivery.name,
            "job_type": delivery.job_type,
            "state": delivery.state,
            "order": delivery.order_id.name,
            "customer": delivery.partner_id.display_name,
            "mobile": delivery.customer_phone or delivery.partner_id.phone,
            "address": delivery.address,
            "maps_url": delivery.google_maps_url,
            "pickup_datetime": delivery.pickup_datetime,
            "delivery_datetime": delivery.delivery_datetime,
            "cash_collected": delivery.cash_collected,
            "currency": delivery.currency_id.name,
        }

    def _log_api(self, name, level="info", payload=None, response=None, status_code=200, started=None, endpoint=None):
        duration = int((time.time() - started) * 1000) if started else 0
        try:
            request.env["aimaze.laundry.integration.log"].sudo().log_event(
                name,
                log_type="api",
                level=level,
                payload=payload,
                response=response,
                status_code=status_code,
                duration_ms=duration,
                endpoint=endpoint or request.httprequest.path,
                method=request.httprequest.method,
            )
        except Exception:
            pass

    @http.route(API_PREFIX + "/auth/customer", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_login_placeholder(self, **kw):
        partner = self._partner()
        return self._success({"authenticated": True, "partner_id": partner.id, "name": partner.display_name, "token_ready": True})

    @http.route(API_PREFIX + "/auth/driver", type="http", auth="user", methods=["GET"], csrf=False)
    def driver_login_placeholder(self, **kw):
        employee = self._employee()
        return self._success({"authenticated": bool(employee), "employee_id": employee.id if employee else False, "name": employee.display_name if employee else False, "token_ready": True})

    @http.route(API_PREFIX + "/auth/staff", type="http", auth="user", methods=["GET"], csrf=False)
    def staff_login_placeholder(self, **kw):
        return self._success({"authenticated": True, "user_id": request.env.user.id, "name": request.env.user.display_name, "token_ready": True})

    @http.route(API_PREFIX + "/customer/profile", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_profile(self, **kw):
        partner = self._partner()
        return self._success({"id": partner.id, "name": partner.display_name, "mobile": partner.phone, "email": partner.email, "vat_trn": partner.laundry_trn})

    @http.route(API_PREFIX + "/customer/orders", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_orders(self, **kw):
        orders, meta = self._paginate("aimaze.laundry.order", self._customer_order_domain())
        return self._success([self._order_json(order) for order in orders], meta=meta)

    @http.route(API_PREFIX + "/customer/orders/<int:order_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_order_detail(self, order_id, **kw):
        order = request.env["aimaze.laundry.order"].search(self._customer_order_domain() + [("id", "=", order_id)], limit=1)
        if not order:
            return self._error("Order not found or access denied.", status=404, code="not_found")
        order._phase4_touch_mobile_access()
        data = self._order_json(order)
        data["lines"] = [{"service": line.service_id.display_name, "name": line.name, "quantity": line.quantity, "subtotal": line.price_subtotal} for line in order.line_ids]
        data["garments"] = [self._garment_json(garment) for garment in order.garment_ids]
        data["deliveries"] = [self._delivery_json(delivery) for delivery in order.delivery_ids]
        return self._success(data)

    @http.route(API_PREFIX + "/customer/garments", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_garments(self, **kw):
        orders = request.env["aimaze.laundry.order"].search(self._customer_order_domain())
        garments, meta = self._paginate("aimaze.laundry.garment", [("order_id", "in", orders.ids)])
        return self._success([self._garment_json(garment) for garment in garments], meta=meta)

    @http.route(API_PREFIX + "/customer/wallet", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_wallet(self, **kw):
        wallets = request.env["aimaze.customer.wallet"].search([("partner_id", "=", self._partner().id), ("company_id", "in", request.env.companies.ids)])
        return self._success([{"id": wallet.id, "company": wallet.company_id.display_name, "currency": wallet.currency_id.name, "balance": wallet.balance} for wallet in wallets])

    @http.route(API_PREFIX + "/customer/wallet/transactions", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_wallet_transactions(self, **kw):
        wallets = request.env["aimaze.customer.wallet"].search([("partner_id", "=", self._partner().id), ("company_id", "in", request.env.companies.ids)])
        txs, meta = self._paginate("aimaze.customer.wallet.transaction", [("wallet_id", "in", wallets.ids)])
        return self._success([{"name": tx.name, "type": tx.transaction_type, "amount": tx.amount, "currency": tx.currency_id.name, "date": tx.date, "state": tx.state} for tx in txs], meta=meta)

    @http.route(API_PREFIX + "/customer/subscriptions", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_subscriptions(self, **kw):
        subs = request.env["aimaze.laundry.subscription"].search([("partner_id", "=", self._partner().id), ("company_id", "in", request.env.companies.ids)])
        return self._success([{"name": sub.name, "package": sub.package_id.display_name, "state": sub.state, "date_end": sub.date_end, "remaining_value": sub.remaining_value, "remaining_quantity": sub.remaining_quantity} for sub in subs])

    @http.route(API_PREFIX + "/customer/pickups", type="http", auth="user", methods=["POST"], csrf=False)
    def customer_pickup_booking(self, **kw):
        payload = self._payload()
        branch = request.env["aimaze.laundry.branch"].search([("company_id", "in", request.env.companies.ids)], limit=1)
        if not branch:
            return self._error("No branch configured for this company.", status=400, code="missing_branch")
        order = request.env["aimaze.laundry.order"].browse(int(payload.get("order_id") or 0))
        if order and order.partner_id.commercial_partner_id != self._partner():
            return self._error("Order access denied.", status=403, code="access_denied")
        if not order:
            order = request.env["aimaze.laundry.order"].sudo().create({"partner_id": self._partner().id, "branch_id": branch.id, "company_id": branch.company_id.id, "pickup_required": True, "source": "mobile_app"})
        delivery = request.env["aimaze.laundry.delivery"].sudo().create({"job_type": "pickup", "order_id": order.id, "partner_id": self._partner().id, "branch_id": branch.id, "address": payload.get("address") or self._partner().contact_address, "remarks": payload.get("remarks")})
        return self._success(self._delivery_json(delivery), status=201)

    @http.route(API_PREFIX + "/customer/complaints", type="http", auth="user", methods=["POST"], csrf=False)
    def customer_complaint_submit(self, **kw):
        payload = self._payload()
        order = request.env["aimaze.laundry.order"].search(self._customer_order_domain() + [("id", "=", int(payload.get("order_id") or 0))], limit=1)
        complaint = request.env["aimaze.laundry.complaint"].sudo().create({"partner_id": self._partner().id, "order_id": order.id, "complaint_type": payload.get("complaint_type") or "other", "notes": payload.get("notes")})
        return self._success({"id": complaint.id, "name": complaint.name, "state": complaint.state}, status=201)

    @http.route(API_PREFIX + "/customer/notifications", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_notifications(self, **kw):
        queues, meta = self._paginate("aimaze.notification.queue", [("partner_id", "=", self._partner().id), ("company_id", "in", request.env.companies.ids)])
        return self._success([{"id": q.id, "event": q.event_type, "message": q.message, "state": q.state, "delivery_status": q.delivery_status, "date": q.create_date} for q in queues], meta=meta)

    @http.route(API_PREFIX + "/customer/invoices", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_invoices(self, **kw):
        invoices, meta = self._paginate("account.move", [("partner_id", "child_of", self._partner().id), ("move_type", "=", "out_invoice"), ("company_id", "in", request.env.companies.ids)])
        return self._success([{"id": inv.id, "name": inv.name, "date": inv.invoice_date, "amount_total": inv.amount_total, "payment_state": inv.payment_state, "currency": inv.currency_id.name} for inv in invoices], meta=meta)

    @http.route(API_PREFIX + "/customer/orders/<int:order_id>/receipt", type="http", auth="user", methods=["GET"], csrf=False)
    def customer_receipt_download(self, order_id, **kw):
        order = request.env["aimaze.laundry.order"].search(self._customer_order_domain() + [("id", "=", order_id)], limit=1)
        if not order:
            return self._error("Order not found or access denied.", status=404, code="not_found")
        return self._success({"download_url": "/report/pdf/aimaze_laundry_management.report_laundry_order_receipt/%s" % order.id})

    @http.route(API_PREFIX + "/driver/jobs", type="http", auth="user", methods=["GET"], csrf=False)
    def driver_jobs(self, **kw):
        jobs, meta = self._paginate("aimaze.laundry.delivery", self._driver_delivery_domain() + [("state", "not in", ("delivered", "cancelled"))])
        return self._success([self._delivery_json(job) for job in jobs], meta=meta)

    @http.route(API_PREFIX + "/driver/jobs/<int:delivery_id>/update", type="http", auth="user", methods=["POST"], csrf=False)
    def driver_job_update(self, delivery_id, **kw):
        payload = self._payload()
        delivery = request.env["aimaze.laundry.delivery"].search(self._driver_delivery_domain() + [("id", "=", delivery_id)], limit=1)
        if not delivery:
            return self._error("Delivery not found or access denied.", status=404, code="not_found")
        vals = {}
        if payload.get("proof_photo"):
            vals["proof_delivery"] = payload.get("proof_photo")
        if payload.get("signature"):
            vals["signature_photo"] = payload.get("signature")
        if payload.get("failed_pickup_reason"):
            vals["failed_pickup_reason"] = payload.get("failed_pickup_reason")
        if payload.get("failed_delivery_reason"):
            vals["failed_delivery_reason"] = payload.get("failed_delivery_reason")
        if vals:
            delivery.sudo().write(vals)
        delivery.sudo().action_mobile_update(state=payload.get("state"), cash_collected=payload.get("cash_collected", False), note=payload.get("note"))
        return self._success(self._delivery_json(delivery))

    @http.route(API_PREFIX + "/driver/jobs/<int:delivery_id>/verify-otp", type="http", auth="user", methods=["POST"], csrf=False)
    def driver_verify_otp(self, delivery_id, **kw):
        payload = self._payload()
        delivery = request.env["aimaze.laundry.delivery"].search(self._driver_delivery_domain() + [("id", "=", delivery_id)], limit=1)
        if not delivery:
            return self._error("Delivery not found or access denied.", status=404, code="not_found")
        verified = bool(delivery.delivery_otp and payload.get("otp") == delivery.delivery_otp)
        return self._success({"verified": verified, "otp_ready": True})

    @http.route(API_PREFIX + "/staff/scan", type="http", auth="user", methods=["POST"], csrf=False)
    def staff_scan(self, **kw):
        payload = self._payload()
        barcode = payload.get("barcode")
        if not barcode:
            return self._error("Barcode is required.", status=400, code="missing_barcode")
        wizard = request.env["aimaze.laundry.scan.wizard"].create({"barcode": barcode, "scan_action": payload.get("scan_action") or "open", "remarks": payload.get("remarks")})
        action = wizard.action_scan()
        return self._success({"res_model": action.get("res_model"), "res_id": action.get("res_id")})

    @http.route(API_PREFIX + "/staff/garments/<int:garment_id>/stage", type="http", auth="user", methods=["POST"], csrf=False)
    def staff_update_garment_stage(self, garment_id, **kw):
        payload = self._payload()
        garment = request.env["aimaze.laundry.garment"].browse(garment_id).exists()
        if not garment:
            return self._error("Garment not found.", status=404, code="not_found")
        garment.action_mobile_stage_update(payload.get("stage"))
        return self._success(self._garment_json(garment))

    @http.route(API_PREFIX + "/staff/qc", type="http", auth="user", methods=["POST"], csrf=False)
    def staff_qc_update(self, **kw):
        payload = self._payload()
        garment = request.env["aimaze.laundry.garment"].browse(int(payload.get("garment_id") or 0)).exists()
        if not garment:
            return self._error("Garment not found.", status=404, code="not_found")
        if payload.get("qc_result"):
            garment.write({"qc_result": payload.get("qc_result")})
        if payload.get("rewash"):
            garment.action_set_stage("rewash")
        return self._success(self._garment_json(garment))
