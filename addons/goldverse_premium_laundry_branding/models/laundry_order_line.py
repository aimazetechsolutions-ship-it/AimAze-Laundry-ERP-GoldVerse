import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LaundryOrderLine(models.Model):
    _inherit = "aimaze.laundry.order.line"

    quantity = fields.Float(default=1.0, digits=(16, 0))
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
    goldverse_colour_ids = fields.Many2many(
        "goldverse.laundry.colour",
        "goldverse_laundry_order_line_colour_rel",
        "line_id",
        "colour_id",
        string="Colour",
        required=True,
    )
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
        required=True,
    )
    goldverse_discount = fields.Char(string="Discount", default="0")
    goldverse_base_price = fields.Monetary(
        string="Base Price",
        compute="_compute_goldverse_price_breakdown",
        store=True,
        currency_field="currency_id",
    )
    goldverse_net_price = fields.Monetary(
        string="Net Price",
        compute="_compute_goldverse_price_breakdown",
        store=True,
        currency_field="currency_id",
    )
    goldverse_discount_amount = fields.Monetary(
        string="Discount",
        compute="_compute_goldverse_price_breakdown",
        store=True,
        currency_field="currency_id",
    )
    goldverse_priority_charge = fields.Monetary(
        string="Priority Chgs",
        compute="_compute_goldverse_price_breakdown",
        store=True,
        currency_field="currency_id",
    )
    goldverse_total_amount = fields.Monetary(
        string="Total Amount",
        compute="_compute_goldverse_total_amount",
        store=True,
        currency_field="currency_id",
    )
    warehouse_sent_datetime = fields.Datetime(string="Sent to Warehouse On", readonly=True, copy=False)
    warehouse_received_datetime = fields.Datetime(string="Received Back On", readonly=True, copy=False)
    warehouse_sent = fields.Boolean(string="Sent to Warehouse", compute="_compute_warehouse_sent", store=True)
    warehouse_received = fields.Boolean(string="Received Back", compute="_compute_warehouse_received", store=True)

    @api.depends("warehouse_sent_datetime")
    def _compute_warehouse_sent(self):
        for line in self:
            line.warehouse_sent = bool(line.warehouse_sent_datetime)

    @api.depends("warehouse_received_datetime")
    def _compute_warehouse_received(self):
        for line in self:
            line.warehouse_received = bool(line.warehouse_received_datetime)

    def action_mark_warehouse_sent(self):
        now = fields.Datetime.now()
        for order in self.mapped("order_id"):
            order._goldverse_validate_send_to_warehouse()
            target_lines = self.filtered(lambda line: line.order_id == order and not line.warehouse_sent_datetime)
            if not target_lines:
                continue
            order._goldverse_create_and_post_invoice()
            if not order.warehouse_collected_datetime:
                order.with_context(goldverse_allow_locked_order_write=True, goldverse_skip_required_validation=True).write({
                    "warehouse_collected_datetime": now,
                    "warehouse_received_datetime": False,
                })
            target_lines.with_context(goldverse_allow_locked_order_write=True).write({
                "warehouse_sent_datetime": now,
                "warehouse_received_datetime": False,
            })
            order.with_context(goldverse_allow_locked_order_write=True, goldverse_skip_required_validation=True)._set_state("warehouse_pending")
        return True

    def action_mark_warehouse_received(self):
        now = fields.Datetime.now()
        for line in self:
            if not line.warehouse_sent_datetime:
                raise UserError(_("Send this line to warehouse before receiving it back at branch."))
            line.with_context(goldverse_allow_locked_order_write=True).write({"warehouse_received_datetime": now})
        for order in self.mapped("order_id").filtered(lambda item: item.state == "warehouse_pending"):
            if (
                order.line_ids
                and all(order.line_ids.mapped("warehouse_sent_datetime"))
                and all(order.line_ids.mapped("warehouse_received_datetime"))
            ):
                safe_order = order.with_context(goldverse_allow_locked_order_write=True, goldverse_skip_required_validation=True)
                safe_order.write({"warehouse_received_datetime": now})
                safe_order._set_state("pending_customer_delivery")
        return True

    def _goldverse_service_detail(self):
        self.ensure_one()
        service = self.service_id
        parts = [
            self.goldverse_category_id.display_name or service.category_id.display_name,
            self.goldverse_subcategory_id.display_name or service.goldverse_subcategory_id.display_name,
            service.name,
        ]
        return " / ".join(part for part in parts if part)

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
            line._goldverse_refresh_amount_fields()

    @api.onchange("goldverse_priority")
    def _onchange_goldverse_priority(self):
        for line in self:
            if line.service_id:
                line.unit_price = line._goldverse_priority_unit_price()
            line._goldverse_refresh_amount_fields()

    @api.onchange("goldverse_subcategory_id")
    def _onchange_goldverse_subcategory_id(self):
        for line in self:
            if line.service_id and line.goldverse_subcategory_id and line.service_id.goldverse_subcategory_id != line.goldverse_subcategory_id:
                line.service_id = False

    @api.onchange("goldverse_colour_id")
    def _onchange_goldverse_colour_id(self):
        for line in self:
            if line.goldverse_colour_id:
                line.goldverse_colour_ids = [(4, line.goldverse_colour_id.id)]
                line.color = line.goldverse_colour_id.name

    @api.onchange("goldverse_colour_ids")
    def _onchange_goldverse_colour_ids(self):
        for line in self:
            if line.goldverse_colour_ids:
                line.color = ", ".join(line.goldverse_colour_ids.mapped("name"))

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

    @api.constrains("service_id", "goldverse_topup_ids")
    def _check_goldverse_topup_required(self):
        missing_lines = self.filtered(lambda line: line.service_id and not line.goldverse_topup_ids)
        if missing_lines:
            raise UserError(_("Add On is mandatory for every laundry order service line."))

    @api.constrains("service_id", "goldverse_colour_ids", "goldverse_colour_id")
    def _check_goldverse_colour_required(self):
        missing_lines = self.filtered(
            lambda line: line.service_id and not (line.goldverse_colour_ids or line.goldverse_colour_id)
        )
        if missing_lines:
            raise UserError(_("Colour is mandatory for every laundry order service line."))

    @api.onchange("goldverse_discount", "quantity", "unit_price")
    def _onchange_goldverse_discount(self):
        for line in self:
            line._goldverse_refresh_amount_fields()

    @api.onchange("tax_ids")
    def _onchange_goldverse_tax_ids(self):
        for line in self:
            line._goldverse_refresh_amount_fields()

    def _goldverse_priority_multiplier(self, priority=False):
        return {
            "express": 1.25,
            "urgent": 1.40,
        }.get(priority or self.goldverse_priority, 1.0)

    def _goldverse_priority_unit_price(self):
        self.ensure_one()
        return (self.service_id.list_price or 0.0) * self._goldverse_priority_multiplier()

    def _goldverse_ensure_unit_price(self):
        for line in self:
            if not line.service_id:
                continue
            expected_price = line._goldverse_priority_unit_price()
            if abs((line.unit_price or 0.0) - expected_price) > 0.0001:
                line.unit_price = expected_price
        return True

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

    def _goldverse_refresh_amount_fields(self):
        for line in self:
            line._goldverse_ensure_unit_price()
            line._compute_goldverse_price_breakdown()
            line._compute_line_amount()
            line._compute_goldverse_total_amount()
        return True

    @api.depends("quantity", "unit_price", "goldverse_discount", "tax_ids")
    def _compute_line_amount(self):
        for line in self:
            line.discount = line._goldverse_discount_percent()
        return super()._compute_line_amount()

    @api.depends("price_subtotal", "price_tax")
    def _compute_goldverse_total_amount(self):
        for line in self:
            line.goldverse_total_amount = line.price_subtotal + line.price_tax

    @api.depends(
        "service_id",
        "service_id.list_price",
        "service_id.goldverse_base_price",
        "goldverse_priority",
        "quantity",
        "unit_price",
    )
    def _compute_goldverse_price_breakdown(self):
        for line in self:
            service = line.service_id
            net_price = service.list_price if service else 0.0
            base_price = service.goldverse_base_price if service and service.goldverse_base_price else net_price
            priority_unit_charge = max((line.unit_price or 0.0) - net_price, 0.0)
            line.goldverse_base_price = base_price
            line.goldverse_discount_amount = max(base_price - net_price, 0.0) * (line.quantity or 0.0)
            line.goldverse_net_price = net_price
            line.goldverse_priority_charge = priority_unit_charge * (line.quantity or 0.0)

    def _goldverse_check_lines_editable(self):
        if self.env.context.get("goldverse_allow_locked_order_write") or self.env.context.get("goldverse_refreshing_amounts"):
            return True
        locked_lines = self.filtered(
            lambda line: line.order_id
            and (line.order_id._goldverse_is_locked() or line.order_id._goldverse_is_created_edit_locked())
        )
        if locked_lines:
            order_names = ", ".join(locked_lines.mapped("order_id.display_name")[:5])
            raise UserError(
                _("Created laundry orders are locked and their item lines cannot be changed. Receive payments or use workflow buttons only. Locked order(s): %s")
                % order_names
            )
        return True

    @api.model
    def _goldverse_check_create_vals_editable(self, vals_list):
        if self.env.context.get("goldverse_allow_locked_order_write") or self.env.context.get("goldverse_refreshing_amounts"):
            return True
        order_ids = [vals.get("order_id") for vals in vals_list if vals.get("order_id")]
        if not order_ids:
            return True
        locked_orders = self.env["aimaze.laundry.order"].browse(order_ids).filtered(
            lambda order: order._goldverse_is_locked() or order._goldverse_is_created_edit_locked()
        )
        if locked_orders:
            order_names = ", ".join(locked_orders.mapped("display_name")[:5])
            raise UserError(
                _("Created laundry orders are locked and new item lines cannot be added. Receive payments or use workflow buttons only. Locked order(s): %s")
                % order_names
            )
        return True

    @api.model_create_multi
    def create(self, vals_list):
        self._goldverse_check_create_vals_editable(vals_list)
        for vals in vals_list:
            vals.setdefault("goldverse_priority", "normal")
            if vals.get("goldverse_topup_id") and not vals.get("goldverse_topup_ids"):
                vals["goldverse_topup_ids"] = [(4, vals["goldverse_topup_id"])]
            self._goldverse_apply_priority_price_vals(vals)
        lines = super().create(vals_list)
        lines._goldverse_sync_display_fields()
        lines._goldverse_refresh_amount_fields()
        lines.mapped("order_id")._goldverse_sync_priority_from_lines()
        return lines

    def write(self, vals):
        self._goldverse_check_lines_editable()
        if self.env.context.get("goldverse_refreshing_amounts"):
            return super().write(vals)
        original_orders = self.mapped("order_id") if "order_id" in vals else self.env["aimaze.laundry.order"]
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
            "goldverse_colour_ids",
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
            self._goldverse_refresh_amount_fields()
        if "goldverse_priority" in vals or "order_id" in vals:
            (original_orders | self.mapped("order_id"))._goldverse_sync_priority_from_lines()
        return result

    def unlink(self):
        self._goldverse_check_lines_editable()
        orders = self.mapped("order_id")
        result = super().unlink()
        orders._goldverse_sync_priority_from_lines()
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
            if line.goldverse_colour_id and line.goldverse_colour_id not in line.goldverse_colour_ids:
                updates["goldverse_colour_ids"] = [(4, line.goldverse_colour_id.id)]
            if line.goldverse_colour_ids:
                colour_names = ", ".join(line.goldverse_colour_ids.mapped("name"))
                if line.color != colour_names:
                    updates["color"] = colour_names
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
            service_detail = line._goldverse_service_detail() if line.service_id else False
            if service_detail and line.description != service_detail:
                updates["description"] = service_detail
            discount_percent = line._goldverse_discount_percent()
            if abs((line.discount or 0.0) - discount_percent) > 0.0001:
                updates["discount"] = discount_percent
            if updates:
                super(LaundryOrderLine, line).write(updates)
        return True

    @api.model
    def _goldverse_sync_all_line_service_details(self):
        lines = self.sudo().with_context(goldverse_allow_locked_order_write=True).search([("service_id", "!=", False)])
        lines._goldverse_sync_display_fields()
        lines._goldverse_refresh_amount_fields()
        for order in lines.mapped("order_id").filtered("invoice_id"):
            normal_invoice_lines = order.invoice_id.invoice_line_ids.filtered(
                lambda line: line.display_type not in ("line_section", "line_note")
                and line.name not in ("Delivery Charges", "Laundry Discount")
            )
            for order_line, invoice_line in zip(order.line_ids, normal_invoice_lines):
                service_detail = order_line._goldverse_service_detail() if order_line.service_id else False
                if service_detail:
                    invoice_line.sudo().write({"name": service_detail})
        return True
