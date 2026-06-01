from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


GOLDVERSE_DELIVERY_TZ = "Asia/Karachi"
GOLDVERSE_DRAFT_ORDER_MARKER = "__GOLDVERSE_DRAFT__"
GOLDVERSE_LOCKED_ORDER_ALLOWED_WRITE_FIELDS = {
    "access_token",
    "access_url",
    "activity_date_deadline",
    "activity_exception_decoration",
    "activity_exception_icon",
    "activity_state",
    "activity_summary",
    "activity_type_icon",
    "activity_type_id",
    "activity_user_id",
    "message_attachment_count",
    "message_follower_ids",
    "message_has_error",
    "message_has_error_counter",
    "message_has_sms_error",
    "message_ids",
    "message_is_follower",
    "message_main_attachment_id",
    "message_needaction",
    "message_needaction_counter",
    "message_partner_ids",
    "my_activity_date_deadline",
}


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

    name = fields.Char(string="Order No.")
    state = fields.Selection(
        selection_add=[
            ("order_created", "Order Created"),
            ("warehouse_pending", "Warehouse Pending"),
            ("received_branch", "Received at Branch"),
            ("pending_customer_delivery", "Pending Delivery to Customer"),
            ("collection", "Collection"),
            ("shift_to_plant", "Shift To Plant"),
            ("in_process", "In-Process at Plant"),
            ("shift_to_outlet", "Shift To Outlet"),
            ("ready_for_delivery", "Ready for Delivery"),
        ],
        ondelete={
            "order_created": "set default",
            "warehouse_pending": "set default",
            "received_branch": "set default",
            "pending_customer_delivery": "set default",
            "collection": "set default",
            "shift_to_plant": "set default",
            "in_process": "set default",
            "shift_to_outlet": "set default",
            "ready_for_delivery": "set default",
        },
    )
    customer_type = fields.Selection(
        selection=[
            ("b2c", "B2C"),
            ("b2b", "B2B"),
        ],
        default=False,
        required=True,
        tracking=True,
    )
    source = fields.Selection(default=False, required=True)
    priority = fields.Selection(default="normal")
    user_id = fields.Many2one("res.users", string="Salesperson", default=lambda self: self.env.user)
    responsible_id = fields.Many2one("hr.employee", string="Responsible Staff", default=lambda self: self._goldverse_default_responsible_employee())
    expected_delivery_datetime = fields.Datetime(string="Delivery Date & Time", default=lambda self: self._goldverse_default_expected_delivery_datetime())
    warehouse_collected_datetime = fields.Datetime(string="Warehouse Collected On", readonly=True, copy=False, tracking=True)
    warehouse_received_datetime = fields.Datetime(string="Received Back From Warehouse On", readonly=True, copy=False, tracking=True)
    goldverse_delivered_to_customer = fields.Boolean(string="Delivered to Customer", readonly=True, copy=False, tracking=True)
    goldverse_actual_delivery_datetime = fields.Datetime(string="Actual Delivery Date & Time", readonly=True, copy=False, tracking=True)
    goldverse_delivery_status = fields.Selection(
        [("undelivered", "Undelivered"), ("delivered", "Delivered")],
        string="State",
        compute="_compute_goldverse_delivery_status",
        store=True,
    )
    goldverse_has_sent_lines = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_has_unsent_lines = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_has_receivable_lines = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_can_send_full_warehouse = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_can_send_lines_warehouse = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_can_receive_lines_warehouse = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")
    goldverse_can_full_receive_warehouse = fields.Boolean(compute="_compute_goldverse_warehouse_line_flags")

    @api.depends("state", "goldverse_delivered_to_customer")
    def _compute_goldverse_delivery_status(self):
        for order in self:
            order.goldverse_delivery_status = "delivered" if order.goldverse_delivered_to_customer or order.state == "delivered" else "undelivered"

    @api.depends(
        "state",
        "line_ids.warehouse_sent_datetime",
        "line_ids.warehouse_received_datetime",
    )
    def _compute_goldverse_warehouse_line_flags(self):
        for order in self:
            lines = order.line_ids
            has_lines = bool(lines)
            has_sent = any(lines.mapped("warehouse_sent_datetime"))
            has_unsent = any(not line.warehouse_sent_datetime for line in lines)
            has_receivable = any(line.warehouse_sent_datetime and not line.warehouse_received_datetime for line in lines)
            send_state = order.state in ("order_created", "invoiced", "warehouse_pending")
            initial_send_state = order.state in ("order_created", "invoiced")

            order.goldverse_has_sent_lines = has_sent
            order.goldverse_has_unsent_lines = has_unsent
            order.goldverse_has_receivable_lines = has_receivable
            order.goldverse_can_send_full_warehouse = has_lines and has_unsent and not has_sent and initial_send_state
            order.goldverse_can_send_lines_warehouse = has_lines and has_unsent and send_state
            order.goldverse_can_receive_lines_warehouse = order.state == "warehouse_pending" and has_receivable
            order.goldverse_can_full_receive_warehouse = (
                order.state == "warehouse_pending"
                and has_lines
                and has_sent
                and not has_unsent
                and has_receivable
            )

    @api.model
    def _goldverse_configure_order_sequence(self):
        sequence = self.env.ref("aimaze_laundry_management.seq_laundry_order", raise_if_not_found=False)
        if not sequence:
            sequence = self.env["ir.sequence"].sudo().search([("code", "=", "aimaze.laundry.order")], limit=1)
        if not sequence:
            return True

        sequence.sudo().write(
            {
                "prefix": "GPL/EME/%(y)s/",
                "padding": 4,
                "use_date_range": False,
                "number_increment": 1,
            }
        )
        if not self.sudo().search_count([]):
            sequence.sudo().write({"number_next_actual": 1})
            sequence.sudo().date_range_ids.write({"number_next_actual": 1})
        return True

    @api.model
    def _goldverse_normalize_document_ref_prefixes(self):
        def quote_identifier(identifier):
            return '"%s"' % identifier.replace('"', '""')

        refs_to_normalize = {
            "aimaze.laundry.order": ("name", "barcode"),
            "account.move": ("name", "ref", "payment_reference", "invoice_origin"),
            "account.move.line": ("name", "ref"),
            "account.payment": ("name", "payment_reference"),
        }
        for model_name, field_names in refs_to_normalize.items():
            model = self.env[model_name].sudo()
            table = model._table
            for field_name in field_names:
                field = model._fields.get(field_name)
                if not field or not field.store or not field.column_type:
                    continue
                query = """
                    UPDATE {table}
                       SET {field} = replace(replace({field}, %s, %s), %s, %s)
                     WHERE {field} LIKE %s OR {field} LIKE %s
                """.format(
                    table=quote_identifier(table),
                    field=quote_identifier(field_name),
                )
                self.env.cr.execute(query, ("GVP/", "GPL/", "GOP/", "GPL/", "%GVP/%", "%GOP/%"))
        return True

    def _goldverse_delivery_timezone(self):
        return pytz.timezone(GOLDVERSE_DELIVERY_TZ)

    def _goldverse_today_bounds_utc(self):
        delivery_tz = self._goldverse_delivery_timezone()
        today = datetime.now(delivery_tz).date()
        local_start = delivery_tz.localize(datetime.combine(today, time.min))
        local_end = delivery_tz.localize(datetime.combine(today, time.max))
        return (
            local_start.astimezone(pytz.UTC).replace(tzinfo=None),
            local_end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def _goldverse_is_today_order_date(self, value):
        if not value:
            return False
        value_dt = fields.Datetime.to_datetime(value)
        if not value_dt.tzinfo:
            value_dt = pytz.UTC.localize(value_dt)
        local_date = value_dt.astimezone(self._goldverse_delivery_timezone()).date()
        return local_date == datetime.now(self._goldverse_delivery_timezone()).date()

    def _goldverse_validate_order_date_today_value(self, value):
        if not self._goldverse_is_today_order_date(value):
            raise ValidationError(_("Order Date must be today's date. Past or future dates are not allowed."))

    def _goldverse_now_order_date(self):
        return fields.Datetime.now()

    def _goldverse_default_expected_delivery_datetime(self):
        delivery_tz = self._goldverse_delivery_timezone()
        today = datetime.now(delivery_tz).date()
        local_deadline = delivery_tz.localize(datetime.combine(today, time(18, 0)))
        return fields.Datetime.to_string(local_deadline.astimezone(pytz.UTC).replace(tzinfo=None))

    def _goldverse_force_six_pm(self, value):
        if not value:
            return value
        delivery_tz = self._goldverse_delivery_timezone()
        value_dt = fields.Datetime.to_datetime(value)
        if not value_dt.tzinfo:
            value_dt = pytz.UTC.localize(value_dt)
        local_dt = value_dt.astimezone(delivery_tz)
        local_six_pm = delivery_tz.localize(datetime.combine(local_dt.date(), time(18, 0)))
        return fields.Datetime.to_string(local_six_pm.astimezone(pytz.UTC).replace(tzinfo=None))

    def _goldverse_default_responsible_employee(self):
        Employee = self.env["hr.employee"].sudo()
        employee = Employee.search([("user_id", "=", self.env.user.id)], limit=1)
        if employee:
            return employee
        return Employee.create({
            "name": self.env.user.name,
            "user_id": self.env.user.id,
            "company_id": self.env.company.id,
            "work_email": self.env.user.email or self.env.user.login,
        })

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        super()._onchange_partner_id()
        for order in self:
            if order.partner_id:
                order.mobile = order.partner_id.mobile or order.partner_id.phone
                order.email = order.partner_id.email

    @api.onchange("customer_type")
    def _onchange_goldverse_customer_type(self):
        for order in self:
            if order.customer_type == "b2b":
                order.source = "corporate_contract"
            elif order.source == "corporate_contract":
                order.source = False
            order.partner_id = False
            order.mobile = False
            order.email = False
        return {"domain": {"partner_id": self._goldverse_partner_domain_for_customer_type()}}

    def _goldverse_partner_domain_for_customer_type(self):
        self.ensure_one()
        base_domain = [("customer_rank", ">", 0)]
        if self.customer_type == "b2b":
            return base_domain + ["|", ("is_company", "=", True), ("laundry_customer_type", "in", ["b2b", "corporate", "hotel", "salon", "gym", "restaurant"])]
        if self.customer_type == "b2c":
            return base_domain + ["|", ("is_company", "=", False), ("laundry_customer_type", "in", [False, "b2c", "walk_in", "individual"])]
        return base_domain

    @api.onchange("expected_delivery_datetime")
    def _onchange_goldverse_expected_delivery_datetime(self):
        return

    @api.onchange("order_date")
    def _onchange_goldverse_order_date(self):
        for order in self:
            if order.order_date and not order._goldverse_is_today_order_date(order.order_date):
                order.order_date = order._goldverse_now_order_date()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "order_date" in fields_list:
            values["order_date"] = self._goldverse_now_order_date()
        if "expected_delivery_datetime" in fields_list:
            values["expected_delivery_datetime"] = self._goldverse_default_expected_delivery_datetime()
        values.setdefault("priority", "normal")
        values.setdefault("user_id", self.env.user.id)
        if "responsible_id" in fields_list and not values.get("responsible_id"):
            employee = self._goldverse_default_responsible_employee()
            if employee:
                values["responsible_id"] = employee.id
        return values

    def _goldverse_prepare_required_order_values(self, vals):
        if vals.get("customer_type") == "b2b":
            vals["source"] = "corporate_contract"
        if not vals.get("order_date"):
            vals["order_date"] = self._goldverse_now_order_date()
        else:
            self._goldverse_validate_order_date_today_value(vals["order_date"])
        if "expected_delivery_datetime" not in vals:
            vals["expected_delivery_datetime"] = self._goldverse_default_expected_delivery_datetime()
        return vals

    def _goldverse_validate_required_order_values(self, vals):
        labels = {
            "partner_id": _("Customer Name"),
            "mobile": _("Mobile"),
            "customer_type": _("Customer Type"),
            "expected_delivery_datetime": _("Delivery Date & Time"),
        }
        values = self.default_get(list(labels))
        values.update(vals)
        if values.get("customer_type") != "b2b":
            labels["source"] = _("Source")
        missing = [label for field_name, label in labels.items() if not values.get(field_name)]
        if missing:
            raise ValidationError(_("Please fill mandatory fields: %s.") % ", ".join(dict.fromkeys(missing)))

    def _goldverse_validate_required_order_fields(self):
        labels = {
            "partner_id": _("Customer Name"),
            "mobile": _("Mobile"),
            "customer_type": _("Customer Type"),
            "expected_delivery_datetime": _("Delivery Date & Time"),
        }
        for order in self:
            order_labels = dict(labels)
            if order.customer_type != "b2b":
                order_labels["source"] = _("Source")
            elif order.source != "corporate_contract":
                order.source = "corporate_contract"
            missing = [label for field_name, label in order_labels.items() if not order[field_name]]
            if missing:
                raise ValidationError(_("Please fill mandatory fields: %s.") % ", ".join(missing))

    def _goldverse_assign_order_number(self):
        sequence = self.env["ir.sequence"].sudo().search([("code", "=", "aimaze.laundry.order")], limit=1)
        for order in self:
            if order.name in (False, "New", GOLDVERSE_DRAFT_ORDER_MARKER):
                order_number = sequence.next_by_id() if sequence else self.env["ir.sequence"].next_by_code("aimaze.laundry.order") or "New"
                order.with_context(goldverse_skip_required_validation=True).write(
                    {
                        "name": order_number,
                        "barcode": order_number,
                    }
                )
            elif not order.barcode or order.barcode in ("New", GOLDVERSE_DRAFT_ORDER_MARKER):
                order.with_context(goldverse_skip_required_validation=True).write({"barcode": order.name})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._goldverse_prepare_required_order_values(vals)
            vals.setdefault("priority", "normal")
            vals.setdefault("user_id", self.env.user.id)
            if not vals.get("responsible_id"):
                employee = self._goldverse_default_responsible_employee()
                if employee:
                    vals["responsible_id"] = employee.id
            self._goldverse_validate_required_order_values(vals)
            if vals.get("name", "New") == "New":
                vals["name"] = GOLDVERSE_DRAFT_ORDER_MARKER
                vals["barcode"] = False
        orders = super().create(vals_list)
        draft_orders = orders.filtered(lambda item: item.name == GOLDVERSE_DRAFT_ORDER_MARKER)
        if draft_orders:
            draft_orders.with_context(goldverse_skip_required_validation=True).write(
                {
                    "name": "New",
                    "barcode": False,
                }
            )
        orders._goldverse_validate_required_order_fields()
        return orders

    def write(self, vals):
        self._goldverse_check_locked_write(vals)
        if vals.get("customer_type") == "b2b":
            vals = dict(vals)
            vals["source"] = "corporate_contract"
        if "order_date" in vals:
            if vals.get("order_date"):
                self._goldverse_validate_order_date_today_value(vals["order_date"])
            else:
                vals = dict(vals)
                vals["order_date"] = self._goldverse_now_order_date()
        result = super().write(vals)
        if not self.env.context.get("goldverse_skip_required_validation"):
            self._goldverse_validate_required_order_fields()
        return result

    def _goldverse_is_locked(self):
        self.ensure_one()
        return self.state == "paid" or (self.payment_status == "paid" and self.balance_amount <= 0.01)

    def _goldverse_check_locked_write(self, vals):
        if self.env.context.get("goldverse_allow_locked_order_write"):
            return True
        if not vals:
            return True
        locked = self.filtered(lambda order: order._goldverse_is_locked())
        if not locked:
            return True
        if set(vals).issubset(GOLDVERSE_LOCKED_ORDER_ALLOWED_WRITE_FIELDS):
            return True
        if set(vals) == {"state"} and vals.get("state") == "paid":
            return True
        names = ", ".join(locked.mapped("display_name")[:5])
        raise UserError(_("Paid laundry orders are locked and cannot be changed. Locked order(s): %s") % names)

    def action_create_order(self):
        self._goldverse_validate_required_order_fields()
        self._goldverse_assign_order_number()
        self._set_state("order_created")

    def _goldverse_validate_receipt_available(self):
        for order in self:
            if order.state == "draft" or not order.name or order.name == "New":
                raise UserError(_("Receipt is available only after Create Order assigns an Order No."))
        return True

    def action_view_receipt(self):
        self.ensure_one()
        self._goldverse_validate_receipt_available()
        return {
            "type": "ir.actions.act_url",
            "name": _("Laundry Order Receipt"),
            "url": "/report/html/aimaze_laundry_management.report_laundry_order_receipt/%s" % self.id,
            "target": "new",
        }

    def action_print_receipt(self):
        self._goldverse_validate_receipt_available()
        return super().action_print_receipt()

    def _goldverse_check_payment_action_allowed(self):
        locked = self.filtered(lambda order: order._goldverse_is_locked())
        if locked:
            names = ", ".join(locked.mapped("display_name")[:5])
            raise UserError(_("This order is fully paid and locked. No further payment action is allowed for: %s") % names)
        return True

    def action_register_advance_payment(self):
        self._goldverse_check_payment_action_allowed()
        return super().action_register_advance_payment()

    def action_register_final_payment(self):
        self._goldverse_check_payment_action_allowed()
        return super().action_register_final_payment()

    def action_use_wallet(self):
        self._goldverse_check_payment_action_allowed()
        return super().action_use_wallet()

    def action_create_invoice(self):
        workflow_states = {
            order.id: order.state
            for order in self
            if order.state in ("order_created", "warehouse_pending", "pending_customer_delivery")
        }
        action = super().action_create_invoice()
        for order in self.filtered(lambda item: item.id in workflow_states and item.invoice_id):
            if order.state == "invoiced":
                order.with_context(goldverse_skip_required_validation=True).write({
                    "state": workflow_states[order.id],
                    "invoice_status": "invoiced",
                })
        return action

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No invoice is linked with this laundry order yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": self.invoice_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _set_state(self, state):
        result = super()._set_state(state)
        self.filtered("invoice_id").write({"invoice_status": "invoiced"})
        return result

    def _goldverse_create_and_post_invoice(self):
        for order in self:
            if order.invoice_id and order.invoice_id.state == "cancel":
                raise UserError(_("The linked invoice for %s is cancelled. Reset or remove it before sending to warehouse.") % order.display_name)
            if not order.invoice_id:
                order.action_create_invoice()
            if order.invoice_id.state == "draft":
                order.invoice_id.action_post()
        return True

    def _goldverse_validate_send_to_warehouse(self):
        missing_lines = self.filtered(lambda order: not order.line_ids)
        if missing_lines:
            raise UserError(_("Add order lines before sending an order to warehouse."))
        invalid_orders = self.filtered(lambda order: order.state not in ("order_created", "invoiced", "warehouse_pending"))
        if invalid_orders:
            raise UserError(_("Only created or invoiced orders can be sent to warehouse."))
        return True

    def action_send_to_warehouse(self):
        self._goldverse_validate_send_to_warehouse()
        if self.filtered(lambda order: any(order.line_ids.mapped("warehouse_sent_datetime"))):
            raise UserError(_("Some lines are already sent to warehouse. Use Send Lines for remaining unsent lines."))
        now = fields.Datetime.now()
        self.write({
            "warehouse_collected_datetime": now,
            "warehouse_received_datetime": False,
        })
        self.mapped("line_ids").write({
            "warehouse_sent_datetime": now,
            "warehouse_received_datetime": False,
        })
        self._goldverse_create_and_post_invoice()
        self._set_state("warehouse_pending")

    def action_mark_received_branch(self):
        now = fields.Datetime.now()
        for order in self:
            if order.state != "warehouse_pending":
                raise UserError(_("Only warehouse pending orders can be marked as received at branch."))
            if not order.line_ids:
                raise UserError(_("No order lines are available to receive."))
            if order.line_ids.filtered(lambda line: not line.warehouse_sent_datetime):
                raise UserError(_("Full receive is available only after all order lines are sent to warehouse. Use Receive Lines for partially sent lines."))
            unreceived_lines = order.line_ids.filtered(lambda line: not line.warehouse_received_datetime)
            unreceived_lines.write({"warehouse_received_datetime": now})
            order.write({"warehouse_received_datetime": now})
            order._set_state("pending_customer_delivery")
        return True

    def action_open_warehouse_sending_lines(self):
        self.ensure_one()
        if self.state not in ("order_created", "invoiced", "warehouse_pending"):
            raise UserError(_("Line-wise sending is available only after the order is created."))
        if not self.line_ids.filtered(lambda line: not line.warehouse_sent_datetime):
            raise UserError(_("All order lines are already sent to warehouse."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Order Lines"),
            "res_model": "aimaze.laundry.order.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("goldverse_premium_laundry_branding.view_laundry_order_line_warehouse_sending_list").id, "list"), (False, "form")],
            "domain": [("order_id", "=", self.id), ("warehouse_sent_datetime", "=", False)],
            "context": {
                "default_order_id": self.id,
                "create": False,
            },
            "target": "current",
        }

    def action_open_warehouse_receiving_lines(self):
        self.ensure_one()
        if self.state != "warehouse_pending":
            raise UserError(_("Line-wise receiving is available only for warehouse pending orders."))
        if not self.line_ids.filtered(lambda line: line.warehouse_sent_datetime and not line.warehouse_received_datetime):
            raise UserError(_("There are no sent lines waiting to be received from warehouse."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Receive Order Lines"),
            "res_model": "aimaze.laundry.order.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("goldverse_premium_laundry_branding.view_laundry_order_line_warehouse_receiving_list").id, "list"), (False, "form")],
            "domain": [("order_id", "=", self.id), ("warehouse_sent_datetime", "!=", False)],
            "context": {
                "default_order_id": self.id,
                "create": False,
            },
            "target": "current",
        }

    def action_stage_collection(self):
        self._set_state("collection")

    def action_stage_shift_to_plant(self):
        self._set_state("shift_to_plant")

    def action_mark_in_process(self):
        self._set_state("in_process")

    def action_stage_shift_to_outlet(self):
        self._set_state("shift_to_outlet")

    def action_stage_ready_for_delivery(self):
        self._set_state("ready_for_delivery")

    def _goldverse_pending_delivery_balance(self):
        self.ensure_one()
        return self.net_balance_amount if "net_balance_amount" in self._fields else self.balance_amount

    def action_mark_delivered(self):
        if self.env.context.get("goldverse_force_mark_delivered"):
            orders = self.with_context(goldverse_allow_locked_order_write=True)
            paid_state_orders = orders.filtered(lambda order: order.state == "paid")
            result = super(LaundryOrder, orders).action_mark_delivered()
            now = fields.Datetime.now()
            orders.write({"goldverse_delivered_to_customer": True})
            orders.filtered(lambda order: not order.goldverse_actual_delivery_datetime).write({"goldverse_actual_delivery_datetime": now})
            paid_orders = orders.filtered(lambda order: order.balance_amount <= 0.01 and order.payment_status == "paid")
            paid_state_or_paid_orders = paid_state_orders | paid_orders
            if paid_state_or_paid_orders:
                paid_state_or_paid_orders._set_state("paid")
            return result
        self.ensure_one()
        if self.state == "paid" and self.goldverse_delivered_to_customer:
            raise UserError(_("This order is already delivered and paid."))
        if self.state not in ("pending_customer_delivery", "paid"):
            return super().action_mark_delivered()
        pending_balance = self._goldverse_pending_delivery_balance()
        if pending_balance and pending_balance > 0.01:
            view = self.env.ref("goldverse_premium_laundry_branding.view_goldverse_delivery_payment_confirm_wizard", raise_if_not_found=False)
            return {
                "type": "ir.actions.act_window",
                "name": _("Delivery Payment Confirmation"),
                "res_model": "goldverse.delivery.payment.confirm.wizard",
                "view_mode": "form",
                "views": [(view.id, "form")] if view else [(False, "form")],
                "target": "new",
                "context": {
                    "default_order_id": self.id,
                    "default_amount_due": pending_balance,
                },
            }
        was_paid_state = self.state == "paid"
        order = self.with_context(goldverse_allow_locked_order_write=True)
        result = super(LaundryOrder, order).action_mark_delivered()
        order.write({"goldverse_delivered_to_customer": True})
        if not order.goldverse_actual_delivery_datetime:
            order.write({"goldverse_actual_delivery_datetime": fields.Datetime.now()})
        if was_paid_state or (order.balance_amount <= 0.01 and order.payment_status == "paid"):
            order._set_state("paid")
        return result

    def action_cancel(self):
        cancellable_states = ("draft", "confirmed", "picked_up", "received", "order_created", "collection", "shift_to_plant")
        blocked = self.filtered(lambda order: order.state not in cancellable_states)
        if blocked:
            raise UserError(_("Orders can be cancelled only before they are sent to warehouse or moved into processing."))
        return super().action_cancel()

    def _goldverse_normalize_order_flow(self):
        old_process_states = ("sorting", "washing", "drying", "ironing", "qc", "packing")
        self.search([("state", "in", ("confirmed", "picked_up", "collection"))]).write({"state": "order_created"})
        self.search([("state", "in", ("received", "shift_to_plant"))]).write({"state": "warehouse_pending"})
        self.search([("state", "in", ("received_branch", "shift_to_outlet", "ready", "out_for_delivery", "ready_for_delivery"))]).write({"state": "pending_customer_delivery"})
        self.search([
            ("state", "=", "invoiced"),
            ("invoice_id", "!=", False),
            ("warehouse_collected_datetime", "=", False),
        ]).write({"state": "order_created"})
        self.search([("state", "in", old_process_states), ("invoice_id", "!=", False)]).write({"state": "invoiced"})
        self.search([("state", "in", old_process_states), ("invoice_id", "=", False)]).write({"state": "in_process"})
        self.search([
            ("state", "=", "delivered"),
            ("goldverse_delivered_to_customer", "=", False),
        ]).with_context(goldverse_allow_locked_order_write=True).write({"goldverse_delivered_to_customer": True})
        self._goldverse_backfill_actual_delivery_datetime()
        return True

    def _goldverse_backfill_actual_delivery_datetime(self):
        Scan = self.env["aimaze.laundry.barcode.scan"].sudo()
        orders = self.sudo().search([
            ("goldverse_actual_delivery_datetime", "=", False),
            "|",
            ("goldverse_delivered_to_customer", "=", True),
            ("state", "=", "delivered"),
        ])
        for order in orders:
            scan = Scan.search([
                ("order_id", "=", order.id),
                ("stage", "=", "delivered"),
            ], order="scan_date desc, id desc", limit=1)
            actual_datetime = scan.scan_date or order.write_date or fields.Datetime.now()
            order.with_context(goldverse_allow_locked_order_write=True).write({
                "goldverse_actual_delivery_datetime": actual_datetime,
            })
        return True

    def _goldverse_normalize_expected_delivery_time(self):
        orders = (self or self.search([])).filtered(
            lambda order: order.expected_delivery_datetime
            and order.state in ("draft", "order_created", "warehouse_pending", "received_branch", "pending_customer_delivery")
        )
        for order in orders:
            order.with_context(goldverse_skip_required_validation=True).write({
                "expected_delivery_datetime": order._goldverse_force_six_pm(order.expected_delivery_datetime),
            })
        return True

    def _phase2_sync_garment_stage(self, order_state):
        if order_state == "in_process":
            for order in self:
                order.garment_ids.filtered(lambda garment: garment.current_stage != "washing").action_set_stage("washing")
            return
        return super()._phase2_sync_garment_stage(order_state)

    @api.depends("state", "expected_delivery_datetime")
    def _compute_phase3_status(self):
        super()._compute_phase3_status()
        stage_order = [
            "draft",
            "order_created",
            "warehouse_pending",
            "received_branch",
            "pending_customer_delivery",
            "in_process",
            "ready_for_delivery",
            "delivered",
            "invoiced",
            "paid",
        ]
        labels = dict(self._fields["state"].selection)
        now = fields.Datetime.now()
        for order in self.filtered(lambda item: item.state in stage_order):
            order.is_delayed = bool(order.state == "in_process" and order.expected_delivery_datetime and order.expected_delivery_datetime < now)
            order.stage_color = "danger" if order.is_delayed else "info"
            order.portal_status = labels.get(order.state, order.state)
            order.operation_progress = stage_order.index(order.state) / (len(stage_order) - 1) * 100.0


class GoldverseDeliveryPaymentConfirmWizard(models.TransientModel):
    _name = "goldverse.delivery.payment.confirm.wizard"
    _description = "GoldVerse Delivery Payment Confirmation"

    order_id = fields.Many2one("aimaze.laundry.order", required=True, readonly=True)
    partner_id = fields.Many2one(related="order_id.partner_id", readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    amount_due = fields.Monetary(string="Pending Payment", currency_field="currency_id", readonly=True)

    def action_receive_payment(self):
        self.ensure_one()
        action = self.order_id._payment_wizard(default_amount=self.amount_due or self.order_id.balance_amount, is_advance=False)
        action["context"] = dict(action.get("context", {}), default_goldverse_deliver_after_payment=True)
        return action

    def action_deliver_without_payment(self):
        self.ensure_one()
        self.order_id.with_context(goldverse_force_mark_delivered=True).action_mark_delivered()
        return {"type": "ir.actions.client", "tag": "reload"}
