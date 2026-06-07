from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class GoldVerseLaundryOrderPickupDelivery(models.Model):
    _inherit = "aimaze.laundry.order"

    goldverse_pickup_delivery_address = fields.Char(string="Pickup / Delivery Address", tracking=True)
    goldverse_pickup_datetime = fields.Datetime(string="Pickup Date & Time", tracking=True)
    goldverse_delivery_zone_id = fields.Many2one("aimaze.laundry.delivery.zone", string="Delivery Zone", tracking=True)
    goldverse_pickup_delivery_note = fields.Char(string="Pickup / Delivery Note", tracking=True)

    @api.onchange("partner_id")
    def _onchange_partner_id_goldverse_pickup_delivery(self):
        for order in self:
            if order.partner_id and not order.goldverse_pickup_delivery_address:
                order.goldverse_pickup_delivery_address = order.partner_id.contact_address

    @api.onchange("pickup_required", "delivery_required")
    def _onchange_goldverse_pickup_delivery_required(self):
        for order in self:
            if (order.pickup_required or order.delivery_required) and order.partner_id and not order.goldverse_pickup_delivery_address:
                order.goldverse_pickup_delivery_address = order.partner_id.contact_address

    @api.onchange("goldverse_pickup_delivery_address")
    def _onchange_goldverse_pickup_delivery_address(self):
        for order in self:
            if order.goldverse_pickup_delivery_address:
                order.goldverse_pickup_delivery_address = order.goldverse_pickup_delivery_address.strip()

    @api.onchange("goldverse_delivery_zone_id")
    def _onchange_goldverse_delivery_zone_id(self):
        for order in self:
            if order.goldverse_delivery_zone_id:
                order.delivery_charge = order.goldverse_delivery_zone_id.delivery_charge or order.delivery_charge

    def _goldverse_validate_required_order_fields(self):
        result = super()._goldverse_validate_required_order_fields()
        for order in self:
            if (order.pickup_required or order.delivery_required) and not order.goldverse_pickup_delivery_address:
                raise ValidationError(_("Please fill Pickup / Delivery Address when pickup or delivery is selected."))
        return result

    def _goldverse_prepare_required_order_values(self, vals):
        vals = super()._goldverse_prepare_required_order_values(vals)
        if (vals.get("pickup_required") or vals.get("delivery_required")) and not vals.get("goldverse_pickup_delivery_address"):
            partner = self.env["res.partner"].browse(vals.get("partner_id")) if vals.get("partner_id") else self.env["res.partner"]
            if partner:
                vals["goldverse_pickup_delivery_address"] = partner.contact_address
        return vals

    def _goldverse_delivery_job_type(self):
        self.ensure_one()
        if self.pickup_required and self.delivery_required:
            return "pickup_delivery"
        if self.pickup_required:
            return "pickup"
        if self.delivery_required:
            return "delivery"
        return False

    def _goldverse_delivery_job_vals(self):
        self.ensure_one()
        job_type = self._goldverse_delivery_job_type()
        if not job_type:
            raise UserError(_("Select Pickup Required, Delivery Required, or both before creating a pickup/delivery job."))
        return {
            "order_id": self.id,
            "job_type": job_type,
            "partner_id": self.partner_id.id,
            "branch_id": self.branch_id.id,
            "zone_id": self.goldverse_delivery_zone_id.id,
            "address": self.goldverse_pickup_delivery_address or self.partner_id.contact_address,
            "pickup_datetime": self.goldverse_pickup_datetime if self.pickup_required else False,
            "delivery_datetime": self.expected_delivery_datetime if self.delivery_required else False,
            "delivery_charge": self.delivery_charge,
            "driver_id": self.driver_id.id,
            "remarks": self.goldverse_pickup_delivery_note,
        }

    def _goldverse_find_active_delivery_job(self):
        self.ensure_one()
        return self.delivery_ids.filtered(lambda job: job.state != "cancelled")[:1]

    def _goldverse_create_or_update_delivery_job(self):
        Delivery = self.env["aimaze.laundry.delivery"]
        jobs = Delivery
        for order in self:
            if not (order.pickup_required or order.delivery_required):
                continue
            vals = order._goldverse_delivery_job_vals()
            job = order._goldverse_find_active_delivery_job()
            if job:
                job.write(vals)
            else:
                job = Delivery.create(vals)
            jobs |= job
        return jobs

    def action_create_pickup_delivery(self):
        self.ensure_one()
        job = self._goldverse_create_or_update_delivery_job()
        if not job:
            raise UserError(_("Select Pickup Required, Delivery Required, or both before creating a pickup/delivery job."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Pickup / Delivery Job"),
            "res_model": "aimaze.laundry.delivery",
            "res_id": job[:1].id,
            "view_mode": "form",
        }

    def action_create_pickup(self):
        for order in self:
            if not order.pickup_required:
                order.with_context(goldverse_allow_locked_order_write=True).pickup_required = True
        return self.action_create_pickup_delivery()

    def action_assign_driver(self):
        for order in self:
            if not order.delivery_required:
                order.with_context(goldverse_allow_locked_order_write=True).delivery_required = True
        return self.action_create_pickup_delivery()

    def action_create_order(self):
        result = super().action_create_order()
        self._goldverse_create_or_update_delivery_job()
        return result


class GoldVerseLaundryDelivery(models.Model):
    _inherit = "aimaze.laundry.delivery"

    order_mobile = fields.Char(related="order_id.mobile", string="Mobile", readonly=True)
    order_email = fields.Char(related="order_id.email", string="Email", readonly=True)
    order_customer_type = fields.Selection(related="order_id.customer_type", string="Customer Type", readonly=True)
    order_expected_delivery_datetime = fields.Datetime(related="order_id.expected_delivery_datetime", string="LO Delivery Date & Time", readonly=True)
    order_amount_total = fields.Monetary(related="order_id.amount_total", string="Order Amount", readonly=True)
    order_payment_status = fields.Selection(related="order_id.payment_status", string="Payment Status", readonly=True)

    @api.model
    def _goldverse_defaults_from_order(self, order):
        return {
            "job_type": order._goldverse_delivery_job_type() or "delivery",
            "partner_id": order.partner_id.id,
            "branch_id": order.branch_id.id,
            "zone_id": order.goldverse_delivery_zone_id.id,
            "address": order.goldverse_pickup_delivery_address or order.partner_id.contact_address,
            "pickup_datetime": order.goldverse_pickup_datetime if order.pickup_required else False,
            "delivery_datetime": order.expected_delivery_datetime if order.delivery_required else False,
            "delivery_charge": order.delivery_charge,
            "driver_id": order.driver_id.id,
            "remarks": order.goldverse_pickup_delivery_note,
        }

    @api.onchange("order_id")
    def _onchange_order_id_goldverse_defaults(self):
        for delivery in self:
            if not delivery.order_id:
                continue
            defaults = delivery._goldverse_defaults_from_order(delivery.order_id)
            for field_name, value in defaults.items():
                delivery[field_name] = value

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for vals in vals_list:
            vals = dict(vals)
            order = self.env["aimaze.laundry.order"].browse(vals.get("order_id")) if vals.get("order_id") else False
            if order:
                defaults = self._goldverse_defaults_from_order(order)
                defaults.update({key: value for key, value in vals.items() if value not in (False, None, "")})
                vals = defaults
                vals["order_id"] = order.id
            prepared_vals.append(vals)
        return super().create(prepared_vals)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("order_id"):
            order = self.env["aimaze.laundry.order"].browse(vals["order_id"])
            defaults = self._goldverse_defaults_from_order(order)
            defaults.update(vals)
            vals = defaults
        return super().write(vals)
