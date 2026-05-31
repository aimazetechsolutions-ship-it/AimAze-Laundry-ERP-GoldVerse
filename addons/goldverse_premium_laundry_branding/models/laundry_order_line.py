import re

from odoo import api, fields, models


class LaundryOrderLine(models.Model):
    _inherit = "aimaze.laundry.order.line"

    goldverse_category_id = fields.Many2one("aimaze.laundry.service.category", string="Category")
    goldverse_subcategory_id = fields.Many2one("goldverse.laundry.subcategory", string="Sub Category")
    goldverse_subcategory = fields.Selection(
        [
            ("wash_fold", "Wash & Fold"),
            ("dry_clean", "Dry Clean"),
            ("pressing", "Pressing"),
            ("ironing", "Ironing"),
            ("stain_removal", "Stain Removal"),
            ("alteration", "Alteration"),
            ("bedding", "Bedding"),
            ("curtain", "Curtain"),
            ("carpet", "Carpet"),
            ("uniform", "Uniform"),
            ("shoe", "Shoe"),
            ("bag", "Bag"),
            ("other", "Other"),
        ],
        string="Sub Category",
    )
    goldverse_priority = fields.Selection(
        [("normal", "Normal"), ("express", "Express"), ("urgent", "Urgent")],
        string="Priority",
        required=True,
        default="normal",
    )
    goldverse_colour_id = fields.Many2one("goldverse.laundry.colour", string="Colour")
    goldverse_colour = fields.Selection(
        [
            ("white", "White"),
            ("black", "Black"),
            ("grey", "Grey"),
            ("silver", "Silver"),
            ("red", "Red"),
            ("maroon", "Maroon"),
            ("pink", "Pink"),
            ("orange", "Orange"),
            ("yellow", "Yellow"),
            ("gold", "Gold"),
            ("green", "Green"),
            ("olive", "Olive"),
            ("blue", "Blue"),
            ("navy", "Navy"),
            ("purple", "Purple"),
            ("brown", "Brown"),
            ("beige", "Beige"),
            ("cream", "Cream"),
            ("multi", "Multi Colour"),
            ("other", "Other"),
        ],
        string="Colour",
    )
    goldverse_qc_option_id = fields.Many2one("goldverse.laundry.qc.option", string="QC")
    goldverse_qc_option_ids = fields.Many2many(
        "goldverse.laundry.qc.option",
        "goldverse_laundry_order_line_qc_rel",
        "line_id",
        "qc_option_id",
        string="QC",
    )
    goldverse_topup_id = fields.Many2one("goldverse.laundry.topup", string="Add On")
    goldverse_topup_ids = fields.Many2many(
        "goldverse.laundry.topup",
        "goldverse_laundry_order_line_topup_rel",
        "line_id",
        "topup_id",
        string="Add On",
    )
    goldverse_discount = fields.Char(string="Discount", default="0")
    goldverse_total_amount = fields.Monetary(
        string="Total Amount",
        compute="_compute_goldverse_total_amount",
        store=True,
        currency_field="currency_id",
    )
    warehouse_sent_datetime = fields.Datetime(string="Sent to Warehouse On", readonly=True, copy=False)
    warehouse_received_datetime = fields.Datetime(string="Received Back On", readonly=True, copy=False)
    warehouse_received = fields.Boolean(string="Received Back", compute="_compute_warehouse_received", store=True)

    @api.depends("warehouse_received_datetime")
    def _compute_warehouse_received(self):
        for line in self:
            line.warehouse_received = bool(line.warehouse_received_datetime)

    def action_mark_warehouse_received(self):
        for line in self:
            if not line.warehouse_sent_datetime:
                line.warehouse_sent_datetime = fields.Datetime.now()
            line.warehouse_received_datetime = fields.Datetime.now()
        return True

    @api.onchange("goldverse_category_id")
    def _onchange_goldverse_category_id(self):
        for line in self:
            if line.service_id and line.goldverse_category_id and line.service_id.category_id != line.goldverse_category_id:
                line.service_id = False

    @api.onchange("service_id")
    def _onchange_service_id(self):
        super()._onchange_service_id()
        for line in self:
            if line.service_id:
                line.goldverse_category_id = line.service_id.category_id
                line.goldverse_subcategory_id = line.service_id.goldverse_subcategory_id
                line.unit_price = line._goldverse_priority_unit_price()

    @api.onchange("goldverse_priority")
    def _onchange_goldverse_priority(self):
        for line in self:
            if line.service_id:
                line.unit_price = line._goldverse_priority_unit_price()

    @api.onchange("goldverse_subcategory_id")
    def _onchange_goldverse_subcategory_id(self):
        for line in self:
            if line.service_id and line.goldverse_subcategory_id and line.service_id.goldverse_subcategory_id != line.goldverse_subcategory_id:
                line.service_id = False

    @api.onchange("goldverse_colour_id")
    def _onchange_goldverse_colour_id(self):
        for line in self:
            if line.goldverse_colour_id:
                line.color = line.goldverse_colour_id.name

    @api.onchange("goldverse_colour")
    def _onchange_goldverse_colour(self):
        for line in self:
            if line.goldverse_colour:
                line.color = dict(line._fields["goldverse_colour"].selection).get(line.goldverse_colour)

    @api.onchange("goldverse_qc_option_id")
    def _onchange_goldverse_qc_option_id(self):
        for line in self:
            if line.goldverse_qc_option_id:
                line.goldverse_qc_option_ids = [(4, line.goldverse_qc_option_id.id)]
                line.qc_status = line.goldverse_qc_option_id.base_qc_status

    @api.onchange("goldverse_qc_option_ids")
    def _onchange_goldverse_qc_option_ids(self):
        for line in self:
            line._goldverse_set_qc_status_from_options()

    @api.onchange("goldverse_topup_id")
    def _onchange_goldverse_topup_id(self):
        for line in self:
            if line.goldverse_topup_id:
                line.goldverse_topup_ids = [(4, line.goldverse_topup_id.id)]

    @api.onchange("goldverse_discount", "quantity", "unit_price")
    def _onchange_goldverse_discount(self):
        for line in self:
            line.discount = line._goldverse_discount_percent()

    def _goldverse_priority_multiplier(self, priority=False):
        return {
            "express": 1.25,
            "urgent": 1.40,
        }.get(priority or self.goldverse_priority, 1.0)

    def _goldverse_priority_unit_price(self):
        self.ensure_one()
        return (self.service_id.list_price or 0.0) * self._goldverse_priority_multiplier()

    @api.model
    def _goldverse_apply_priority_price_vals(self, vals):
        if not vals.get("service_id"):
            return vals
        if "unit_price" in vals and "goldverse_priority" not in vals:
            return vals
        service = self.env["aimaze.laundry.service"].browse(vals["service_id"])
        priority = vals.get("goldverse_priority") or "normal"
        vals["unit_price"] = (service.list_price or 0.0) * self._goldverse_priority_multiplier(priority)
        return vals

    def _goldverse_discount_percent(self):
        self.ensure_one()
        base = (self.quantity or 0.0) * (self.unit_price or 0.0)
        raw = (self.goldverse_discount or "").strip()
        if not raw or raw == "0":
            return 0.0
        number_match = re.search(r"-?\d+(?:\.\d+)?", raw)
        if not number_match:
            return 0.0
        value = float(number_match.group(0))
        if "%" in raw:
            return max(0.0, min(value, 100.0))
        if not base:
            return 0.0
        return max(0.0, min((value / base) * 100.0, 100.0))

    @api.depends("quantity", "unit_price", "goldverse_discount", "tax_ids")
    def _compute_line_amount(self):
        for line in self:
            line.discount = line._goldverse_discount_percent()
        return super()._compute_line_amount()

    @api.depends("price_subtotal", "price_tax")
    def _compute_goldverse_total_amount(self):
        for line in self:
            line.goldverse_total_amount = line.price_subtotal + line.price_tax

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("goldverse_priority", "normal")
            self._goldverse_apply_priority_price_vals(vals)
        lines = super().create(vals_list)
        lines._goldverse_sync_display_fields()
        return lines

    def write(self, vals):
        if {"service_id", "goldverse_priority"} & set(vals) and "unit_price" not in vals:
            for line in self:
                service_id = vals.get("service_id") or line.service_id.id
                if not service_id:
                    continue
                service = self.env["aimaze.laundry.service"].browse(service_id)
                priority = vals.get("goldverse_priority") or line.goldverse_priority or "normal"
                super(LaundryOrderLine, line).write({
                    "unit_price": (service.list_price or 0.0) * line._goldverse_priority_multiplier(priority)
                })
        result = super().write(vals)
        if {
            "service_id",
            "goldverse_priority",
            "goldverse_subcategory_id",
            "goldverse_colour_id",
            "goldverse_qc_option_id",
            "goldverse_qc_option_ids",
            "goldverse_topup_id",
            "goldverse_topup_ids",
            "goldverse_colour",
            "color",
            "goldverse_discount",
            "quantity",
            "unit_price",
        } & set(vals):
            self._goldverse_sync_display_fields()
        return result

    def _goldverse_set_qc_status_from_options(self):
        self.ensure_one()
        statuses = self.goldverse_qc_option_ids.mapped("base_qc_status")
        if "fail" in statuses:
            self.qc_status = "fail"
        elif "rewash" in statuses:
            self.qc_status = "rewash"
        elif "pass" in statuses:
            self.qc_status = "pass"
        else:
            self.qc_status = "pending"

    def _goldverse_sync_display_fields(self):
        for line in self:
            updates = {}
            if line.service_id and line.goldverse_category_id != line.service_id.category_id:
                updates["goldverse_category_id"] = line.service_id.category_id.id
            if line.service_id and line.service_id.goldverse_subcategory_id and line.goldverse_subcategory_id != line.service_id.goldverse_subcategory_id:
                updates["goldverse_subcategory_id"] = line.service_id.goldverse_subcategory_id.id
            if line.goldverse_colour_id and line.color != line.goldverse_colour_id.name:
                updates["color"] = line.goldverse_colour_id.name
            if line.goldverse_qc_option_id and line.qc_status != line.goldverse_qc_option_id.base_qc_status:
                updates["qc_status"] = line.goldverse_qc_option_id.base_qc_status
            if line.goldverse_qc_option_id and line.goldverse_qc_option_id not in line.goldverse_qc_option_ids:
                updates["goldverse_qc_option_ids"] = [(4, line.goldverse_qc_option_id.id)]
            if line.goldverse_topup_id and line.goldverse_topup_id not in line.goldverse_topup_ids:
                updates["goldverse_topup_ids"] = [(4, line.goldverse_topup_id.id)]
            if line.goldverse_qc_option_ids:
                statuses = line.goldverse_qc_option_ids.mapped("base_qc_status")
                qc_status = "fail" if "fail" in statuses else "rewash" if "rewash" in statuses else "pass" if "pass" in statuses else "pending"
                if line.qc_status != qc_status:
                    updates["qc_status"] = qc_status
            if line.goldverse_colour:
                updates["color"] = dict(line._fields["goldverse_colour"].selection).get(line.goldverse_colour)
            discount_percent = line._goldverse_discount_percent()
            if abs((line.discount or 0.0) - discount_percent) > 0.0001:
                updates["discount"] = discount_percent
            if updates:
                super(LaundryOrderLine, line).write(updates)
        return True
