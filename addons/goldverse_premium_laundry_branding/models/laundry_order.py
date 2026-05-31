from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

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

    def _goldverse_default_expected_delivery_datetime(self):
        user_tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        today = fields.Date.context_today(self)
        local_deadline = user_tz.localize(datetime.combine(today, time(18, 0)))
        return fields.Datetime.to_string(local_deadline.astimezone(pytz.UTC).replace(tzinfo=None))

    def _goldverse_force_six_pm(self, value):
        if not value:
            return value
        user_tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        value_dt = fields.Datetime.to_datetime(value)
        if not value_dt.tzinfo:
            value_dt = pytz.UTC.localize(value_dt)
        local_dt = value_dt.astimezone(user_tz)
        local_six_pm = user_tz.localize(datetime.combine(local_dt.date(), time(18, 0)))
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
        for order in self:
            if order.expected_delivery_datetime:
                order.expected_delivery_datetime = order._goldverse_force_six_pm(order.expected_delivery_datetime)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
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
        if "expected_delivery_datetime" not in vals:
            vals["expected_delivery_datetime"] = self._goldverse_default_expected_delivery_datetime()
        elif vals.get("expected_delivery_datetime"):
            vals["expected_delivery_datetime"] = self._goldverse_force_six_pm(vals["expected_delivery_datetime"])
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
        orders = super().create(vals_list)
        sequence = self.env["ir.sequence"].sudo().search([("code", "=", "aimaze.laundry.order")], limit=1)
        for order in orders.filtered(lambda item: item.name == "New"):
            order.name = sequence.next_by_id() if sequence else self.env["ir.sequence"].next_by_code("aimaze.laundry.order") or "New"
            order.barcode = order.name
        orders._goldverse_validate_required_order_fields()
        return orders

    def write(self, vals):
        if vals.get("customer_type") == "b2b":
            vals = dict(vals)
            vals["source"] = "corporate_contract"
        if vals.get("expected_delivery_datetime"):
            vals = dict(vals)
            vals["expected_delivery_datetime"] = self._goldverse_force_six_pm(vals["expected_delivery_datetime"])
        result = super().write(vals)
        if not self.env.context.get("goldverse_skip_required_validation"):
            self._goldverse_validate_required_order_fields()
        return result

    def action_create_order(self):
        self._goldverse_validate_required_order_fields()
        self._set_state("order_created")

    def action_view_receipt(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "name": _("Laundry Order Receipt"),
            "url": "/report/html/aimaze_laundry_management.report_laundry_order_receipt/%s" % self.id,
            "target": "new",
        }

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

    def action_send_to_warehouse(self):
        missing_lines = self.filtered(lambda order: not order.line_ids)
        if missing_lines:
            raise UserError(_("Add order lines before sending an order to warehouse."))
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
        for order in self:
            unreceived_lines = order.line_ids.filtered(lambda line: not line.warehouse_received_datetime)
            if unreceived_lines:
                missing_names = ", ".join(unreceived_lines.mapped("display_name")[:5])
                raise UserError(_("Receive all warehouse lines before marking the order received. Missing: %s") % missing_names)
        self.write({"warehouse_received_datetime": fields.Datetime.now()})
        self._set_state("pending_customer_delivery")

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
        self.search([("state", "in", old_process_states), ("invoice_id", "!=", False)]).write({"state": "invoiced"})
        self.search([("state", "in", old_process_states), ("invoice_id", "=", False)]).write({"state": "in_process"})
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
