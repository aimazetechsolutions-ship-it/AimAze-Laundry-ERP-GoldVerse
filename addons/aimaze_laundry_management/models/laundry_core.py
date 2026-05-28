from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    laundry_branch_ids = fields.Many2many(
        "aimaze.laundry.branch",
        "aimaze_laundry_branch_user_rel",
        "user_id",
        "branch_id",
        string="Allowed Laundry Branches",
    )


class ResPartner(models.Model):
    _inherit = "res.partner"

    laundry_customer_type = fields.Selection(
        [
            ("walk_in", "Walk-in"),
            ("individual", "Individual"),
            ("corporate", "Corporate"),
            ("hotel", "Hotel"),
            ("salon", "Salon"),
            ("gym", "Gym"),
            ("restaurant", "Restaurant"),
            ("other", "Other"),
        ],
        string="Laundry Customer Type",
    )
    laundry_contract_id = fields.Many2one("aimaze.laundry.contract", string="Active Laundry Contract")
    laundry_loyalty_points = fields.Float(string="Laundry Loyalty Points", default=0.0)
    laundry_wallet_balance = fields.Monetary(string="Laundry Wallet Balance", currency_field="currency_id")
    laundry_branch_id = fields.Many2one("aimaze.laundry.branch", string="Default Laundry Branch")


class ResCompany(models.Model):
    _inherit = "res.company"

    def _aimaze_country_from_currency(self):
        self.ensure_one()
        xml_id_by_currency = {
            "AED": "base.ae",
            "PKR": "base.pk",
        }
        xml_id = xml_id_by_currency.get(self.currency_id.name)
        return self.env.ref(xml_id, raise_if_not_found=False) if xml_id else self.env["res.country"]

    def _aimaze_fix_laundry_country_defaults(self):
        """Align obvious country/currency mismatches without overriding valid setup."""
        companies = self.search([])
        for company in companies:
            expected_country = company._aimaze_country_from_currency()
            if expected_country and (not company.country_id or company.country_id.code == "US"):
                company.country_id = expected_country
        return True


class LaundryBranch(models.Model):
    _name = "aimaze.laundry.branch"
    _description = "Laundry Branch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, code"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, tracking=True)
    country_id = fields.Many2one("res.country", related="company_id.country_id", store=True, readonly=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    address = fields.Char()
    phone = fields.Char()
    manager_id = fields.Many2one("res.users", tracking=True)
    warehouse_id = fields.Many2one("stock.warehouse")
    stock_location_id = fields.Many2one("stock.location", string="Laundry Stock Location")
    default_journal_id = fields.Many2one("account.journal", domain="[('company_id', '=', company_id)]")
    sale_journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]")
    cash_journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'cash'), ('company_id', '=', company_id)]")
    bank_journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]")
    user_ids = fields.Many2many("res.users", string="Branch Users")
    active = fields.Boolean(default=True)

    _code_company_unique = models.Constraint("UNIQUE(code, company_id)", "Branch code must be unique per company.")


class LaundryServiceCategory(models.Model):
    _name = "aimaze.laundry.service.category"
    _description = "Laundry Service Category"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class LaundryService(models.Model):
    _name = "aimaze.laundry.service"
    _description = "Laundry Service"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "category_id, name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char()
    category_id = fields.Many2one("aimaze.laundry.service.category", required=True)
    product_id = fields.Many2one("product.product", string="Linked Product")
    pricing_method = fields.Selection(
        [("piece", "Per Piece"), ("kg", "Per Kg"), ("sqm", "Per Sqm"), ("fixed", "Fixed")],
        default="piece",
        required=True,
    )
    list_price = fields.Monetary(currency_field="currency_id", required=True)
    express_surcharge_percent = fields.Float(default=50.0)
    urgent_surcharge_percent = fields.Float(default=25.0)
    delivery_charge = fields.Monetary(currency_field="currency_id")
    tax_applicable = fields.Boolean(default=True)
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    income_account_id = fields.Many2one("account.account", domain="[('account_type', '=', 'income')]")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        services = super().create(vals_list)
        services._sync_products()
        return services

    def write(self, vals):
        result = super().write(vals)
        if {"name", "list_price", "code", "income_account_id", "tax_ids"} & set(vals):
            self._sync_products()
        return result

    def _sync_products(self):
        Product = self.env["product.product"].sudo()
        for service in self:
            values = {
                "name": service.name,
                "default_code": service.code or service.name,
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "list_price": service.list_price,
                "taxes_id": [(6, 0, service.tax_ids.ids)],
            }
            if service.income_account_id:
                values["property_account_income_id"] = service.income_account_id.id
            if service.product_id:
                service.product_id.write(values)
            else:
                service.product_id = Product.create(values).id


class LaundryRateCard(models.Model):
    _name = "aimaze.laundry.rate.card"
    _description = "Laundry Rate Card"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    partner_id = fields.Many2one("res.partner", string="Corporate Customer")
    date_from = fields.Date()
    date_to = fields.Date()
    line_ids = fields.One2many("aimaze.laundry.rate.card.line", "rate_card_id")
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)


class LaundryRateCardLine(models.Model):
    _name = "aimaze.laundry.rate.card.line"
    _description = "Laundry Rate Card Line"

    rate_card_id = fields.Many2one("aimaze.laundry.rate.card", required=True, ondelete="cascade")
    service_id = fields.Many2one("aimaze.laundry.service", required=True)
    pricing_method = fields.Selection(related="service_id.pricing_method", store=True, readonly=True)
    price = fields.Monetary(currency_field="currency_id", required=True)
    min_qty = fields.Float(default=1.0)
    express_surcharge_percent = fields.Float(default=50.0)
    urgent_surcharge_percent = fields.Float(default=25.0)
    currency_id = fields.Many2one(related="rate_card_id.currency_id", store=True, readonly=True)


class LaundryContract(models.Model):
    _name = "aimaze.laundry.contract"
    _description = "Laundry Corporate / B2B Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    rate_card_id = fields.Many2one("aimaze.laundry.rate.card")
    date_start = fields.Date(required=True)
    date_end = fields.Date()
    credit_limit = fields.Monetary(currency_field="currency_id")
    billing_cycle = fields.Selection([("monthly", "Monthly"), ("weekly", "Weekly"), ("manual", "Manual")], default="monthly")
    pickup_schedule = fields.Text()
    payment_term_id = fields.Many2one("account.payment.term")
    sla_hours = fields.Float(default=48.0)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("hold", "On Hold"), ("expired", "Expired"), ("cancelled", "Cancelled")],
        default="draft",
        tracking=True,
    )
    order_ids = fields.One2many("aimaze.laundry.order", "contract_id")
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.contract") or "New"
        contracts = super().create(vals_list)
        contracts.partner_id.write({"laundry_customer_type": "corporate"})
        return contracts

    def action_activate(self):
        self.write({"state": "active"})

    def action_monthly_invoice(self):
        for contract in self:
            orders = contract.order_ids.filtered(lambda order: order.state not in ("cancelled",) and not order.invoice_id)
            if not orders:
                raise UserError(_("No uninvoiced orders found for %s.") % contract.display_name)
            invoice_lines = []
            for order in orders:
                invoice_lines.append((0, 0, {"name": order.name, "quantity": 1, "price_unit": order.amount_total}))
            move = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": contract.partner_id.id,
                    "invoice_date": fields.Date.context_today(self),
                    "company_id": contract.company_id.id,
                    "currency_id": contract.currency_id.id,
                    "laundry_contract_id": contract.id,
                    "invoice_payment_term_id": contract.payment_term_id.id,
                    "invoice_line_ids": invoice_lines,
                }
            )
            orders.write({"invoice_id": move.id, "invoice_status": "invoiced"})
            return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id, "view_mode": "form"}


class LaundryOrder(models.Model):
    _name = "aimaze.laundry.order"
    _description = "Laundry Order"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True, tracking=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, tracking=True)
    mobile = fields.Char()
    email = fields.Char(related="partner_id.email", readonly=False)
    customer_type = fields.Selection(
        [
            ("walk_in", "Walk-in"),
            ("individual", "Individual"),
            ("corporate", "Corporate"),
            ("hotel", "Hotel"),
            ("salon", "Salon"),
            ("gym", "Gym"),
            ("restaurant", "Restaurant"),
            ("other", "Other"),
        ],
        default="walk_in",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True, tracking=True)
    country_id = fields.Many2one("res.country", related="company_id.country_id", store=True, readonly=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    order_date = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    expected_delivery_datetime = fields.Datetime(tracking=True)
    pickup_required = fields.Boolean()
    delivery_required = fields.Boolean()
    source = fields.Selection(
        [
            ("walk_in", "Walk-in"),
            ("phone", "Phone"),
            ("whatsapp", "WhatsApp"),
            ("website", "Website"),
            ("mobile_app", "Mobile App"),
            ("corporate_contract", "Corporate Contract"),
        ],
        default="walk_in",
        required=True,
    )
    service_type = fields.Selection(
        [
            ("wash", "Wash"),
            ("dry_clean", "Dry Clean"),
            ("ironing", "Ironing"),
            ("wash_fold", "Wash & Fold"),
            ("wash_iron", "Wash & Iron"),
            ("carpet", "Carpet Cleaning"),
            ("shoe", "Shoe Cleaning"),
            ("curtain", "Curtain Cleaning"),
            ("express", "Express Service"),
            ("other", "Other"),
        ],
        default="wash_fold",
        required=True,
    )
    priority = fields.Selection([("normal", "Normal"), ("urgent", "Urgent"), ("express", "Express")], default="normal")
    user_id = fields.Many2one("res.users", string="Salesperson", default=lambda self: self.env.user)
    responsible_id = fields.Many2one("hr.employee", string="Responsible Staff")
    driver_id = fields.Many2one("hr.employee")
    contract_id = fields.Many2one("aimaze.laundry.contract")
    line_ids = fields.One2many("aimaze.laundry.order.line", "order_id")
    delivery_ids = fields.One2many("aimaze.laundry.delivery", "order_id")
    qc_ids = fields.One2many("aimaze.laundry.qc", "order_id")
    complaint_ids = fields.One2many("aimaze.laundry.complaint", "order_id")
    task_ids = fields.One2many("aimaze.laundry.staff.task", "order_id")
    total_qty = fields.Float(compute="_compute_amounts", store=True)
    amount_untaxed = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    amount_tax = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    discount_amount = fields.Monetary(currency_field="currency_id")
    delivery_charge = fields.Monetary(currency_field="currency_id")
    amount_total = fields.Monetary(compute="_compute_amounts", store=True, currency_field="currency_id")
    advance_paid = fields.Monetary(compute="_compute_payment_totals", store=True, currency_field="currency_id")
    paid_amount = fields.Monetary(compute="_compute_payment_totals", store=True, currency_field="currency_id")
    balance_amount = fields.Monetary(compute="_compute_payment_totals", store=True, currency_field="currency_id")
    payment_status = fields.Selection(
        [("unpaid", "Unpaid"), ("partial", "Partially Paid"), ("paid", "Paid"), ("refunded", "Refunded")],
        compute="_compute_payment_totals",
        store=True,
    )
    invoice_status = fields.Selection(
        [("no", "Nothing to Invoice"), ("to_invoice", "To Invoice"), ("invoiced", "Invoiced")],
        default="no",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("picked_up", "Picked Up"),
            ("received", "Received"),
            ("sorting", "Sorting"),
            ("washing", "Washing"),
            ("drying", "Drying"),
            ("ironing", "Ironing"),
            ("qc", "QC"),
            ("packing", "Packing"),
            ("ready", "Ready"),
            ("out_for_delivery", "Out for Delivery"),
            ("delivered", "Delivered"),
            ("invoiced", "Invoiced"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    notes = fields.Text()
    internal_remarks = fields.Text()
    damage_remarks = fields.Text()
    stain_remarks = fields.Text()
    customer_special_instructions = fields.Text()
    invoice_id = fields.Many2one("account.move", readonly=True, copy=False)
    payment_ids = fields.One2many("account.payment", "aimaze_laundry_order_id", readonly=True)
    barcode = fields.Char(copy=False, readonly=True)
    access_url = fields.Char(compute="_compute_access_url")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for order in self:
            if order.partner_id:
                order.mobile = order.partner_id.phone
                order.email = order.partner_id.email
                if order.partner_id.laundry_customer_type:
                    order.customer_type = order.partner_id.laundry_customer_type

    @api.depends("name")
    def _compute_access_url(self):
        for order in self:
            order.access_url = "/my/laundry/orders/%s" % order.id

    @api.depends("line_ids.price_subtotal", "line_ids.price_tax", "line_ids.quantity", "discount_amount", "delivery_charge")
    def _compute_amounts(self):
        for order in self:
            untaxed = sum(order.line_ids.mapped("price_subtotal"))
            tax = sum(order.line_ids.mapped("price_tax"))
            order.total_qty = sum(order.line_ids.mapped("quantity"))
            order.amount_untaxed = untaxed
            order.amount_tax = tax
            order.amount_total = max(untaxed + tax + order.delivery_charge - order.discount_amount, 0.0)

    @api.depends("amount_total", "payment_ids.amount", "payment_ids.state")
    def _compute_payment_totals(self):
        for order in self:
            posted = order.payment_ids.filtered(lambda p: p.state in ("paid", "posted", "in_process"))
            paid = sum(posted.mapped("amount"))
            order.advance_paid = paid
            order.paid_amount = paid
            order.balance_amount = max(order.amount_total - paid, 0.0)
            if paid <= 0:
                order.payment_status = "unpaid"
            elif order.balance_amount > 0.01:
                order.payment_status = "partial"
            else:
                order.payment_status = "paid"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.order") or "New"
            vals.setdefault("barcode", vals.get("name"))
        orders = super().create(vals_list)
        for order in orders:
            order.barcode = order.name
            order.partner_id.laundry_customer_type = order.customer_type
        return orders

    def _set_state(self, state):
        self.write({"state": state})
        if state not in ("draft", "cancelled"):
            self.write({"invoice_status": "to_invoice"})
        self._create_scan_log(state)

    def _create_scan_log(self, state):
        Scan = self.env["aimaze.laundry.barcode.scan"]
        for order in self:
            Scan.create({"order_id": order.id, "stage": state, "scan_type": "manual", "branch_id": order.branch_id.id})

    def action_confirm(self):
        self._set_state("confirmed")

    def action_create_pickup(self):
        return self._create_delivery_job("pickup")

    def action_mark_received(self):
        self._set_state("received")

    def action_start_washing(self):
        self._set_state("washing")

    def action_start_ironing(self):
        self._set_state("ironing")

    def action_start_qc(self):
        self._set_state("qc")

    def action_mark_ready(self):
        self._set_state("ready")

    def action_assign_driver(self):
        return self._create_delivery_job("delivery")

    def action_mark_delivered(self):
        self._set_state("delivered")

    def action_cancel(self):
        self._set_state("cancelled")

    def action_register_advance_payment(self):
        return self._payment_wizard(default_amount=self.balance_amount or self.amount_total, is_advance=True)

    def action_register_final_payment(self):
        return self._payment_wizard(default_amount=self.balance_amount, is_advance=False)

    def _payment_wizard(self, default_amount, is_advance):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Register Laundry Payment"),
            "res_model": "aimaze.laundry.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_amount": default_amount,
                "default_is_advance": is_advance,
            },
        }

    def _create_delivery_job(self, job_type):
        self.ensure_one()
        job = self.env["aimaze.laundry.delivery"].create(
            {
                "order_id": self.id,
                "job_type": job_type,
                "partner_id": self.partner_id.id,
                "branch_id": self.branch_id.id,
                "address": self.partner_id.contact_address,
                "delivery_charge": self.delivery_charge,
                "driver_id": self.driver_id.id,
            }
        )
        return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.delivery", "res_id": job.id, "view_mode": "form"}

    def action_create_pickup_delivery(self):
        self.ensure_one()
        if self.pickup_required and self.delivery_required:
            return self._create_delivery_job("pickup_delivery")
        if self.pickup_required:
            return self._create_delivery_job("pickup")
        return self._create_delivery_job("delivery")

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.invoice_id.id, "view_mode": "form"}
        if not self.line_ids:
            raise UserError(_("Add at least one garment/service line before invoicing."))
        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": line.product_id.id,
                        "name": line.description or line.name,
                        "quantity": line.quantity,
                        "price_unit": line.unit_price,
                        "discount": line.discount,
                        "tax_ids": [(6, 0, line.tax_ids.ids)],
                    },
                )
            )
        if self.delivery_charge:
            invoice_lines.append((0, 0, {"name": _("Delivery Charges"), "quantity": 1, "price_unit": self.delivery_charge}))
        if self.discount_amount:
            invoice_lines.append((0, 0, {"name": _("Laundry Discount"), "quantity": 1, "price_unit": -self.discount_amount}))
        journal = self.branch_id.sale_journal_id or self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_("Configure a sales journal for company %s or on branch %s before creating invoices.") % (self.company_id.display_name, self.branch_id.display_name))
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_id.id,
                "invoice_origin": self.name,
                "invoice_date": fields.Date.context_today(self),
                "company_id": self.company_id.id,
                "currency_id": self.currency_id.id,
                "journal_id": journal.id,
                "laundry_order_id": self.id,
                "laundry_branch_id": self.branch_id.id,
                "invoice_line_ids": invoice_lines,
            }
        )
        self.write({"invoice_id": invoice.id, "invoice_status": "invoiced", "state": "invoiced"})
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": invoice.id, "view_mode": "form"}

    def action_print_receipt(self):
        return self.env.ref("aimaze_laundry_management.action_report_laundry_order_receipt").report_action(self)

    def action_print_garment_tags(self):
        return self.env.ref("aimaze_laundry_management.action_report_laundry_garment_tags").report_action(self)


class LaundryOrderLine(models.Model):
    _name = "aimaze.laundry.order.line"
    _description = "Laundry Order / Garment Line"
    _order = "order_id, id"

    order_id = fields.Many2one("aimaze.laundry.order", required=True, ondelete="cascade")
    service_id = fields.Many2one("aimaze.laundry.service", required=True)
    product_id = fields.Many2one("product.product", related="service_id.product_id", store=True, readonly=True)
    garment_category = fields.Char()
    garment_item = fields.Char()
    name = fields.Char(required=True, default="/")
    description = fields.Char()
    color = fields.Char()
    brand = fields.Char()
    quantity = fields.Float(default=1.0)
    unit_price = fields.Monetary(currency_field="currency_id")
    discount = fields.Float()
    tax_ids = fields.Many2many("account.tax")
    price_subtotal = fields.Monetary(compute="_compute_line_amount", store=True, currency_field="currency_id")
    price_tax = fields.Monetary(compute="_compute_line_amount", store=True, currency_field="currency_id")
    barcode = fields.Char(copy=False)
    tag_number = fields.Char(copy=False)
    condition_before = fields.Text()
    stain_details = fields.Text()
    damage_details = fields.Text()
    special_instruction = fields.Text()
    process_status = fields.Selection(related="order_id.state", store=True, readonly=True)
    qc_status = fields.Selection([("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("rewash", "Rewash")], default="pending")
    rewash_required = fields.Boolean()
    lost_item = fields.Boolean()
    compensation_amount = fields.Monetary(currency_field="currency_id")
    company_id = fields.Many2one(related="order_id.company_id", store=True, readonly=True)
    branch_id = fields.Many2one(related="order_id.branch_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True, readonly=True)

    @api.onchange("service_id")
    def _onchange_service_id(self):
        for line in self:
            if line.service_id:
                line.name = line.service_id.name
                line.unit_price = line.service_id.list_price
                line.tax_ids = line.service_id.tax_ids

    @api.depends("quantity", "unit_price", "discount", "tax_ids")
    def _compute_line_amount(self):
        for line in self:
            base = line.quantity * line.unit_price * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_ids.compute_all(base, currency=line.currency_id, quantity=1.0, product=line.product_id, partner=line.order_id.partner_id)
            line.price_subtotal = taxes["total_excluded"] if taxes else base
            line.price_tax = (taxes["total_included"] - taxes["total_excluded"]) if taxes else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if not line.tag_number:
                line.tag_number = self.env["ir.sequence"].next_by_code("aimaze.laundry.garment.tag") or line.id
            if not line.barcode:
                line.barcode = "%s-%s" % (line.order_id.name, line.tag_number)
        return lines


class LaundryDeliveryZone(models.Model):
    _name = "aimaze.laundry.delivery.zone"
    _description = "Laundry Delivery Zone"
    _order = "name"

    name = fields.Char(required=True)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    delivery_charge = fields.Monetary(currency_field="currency_id")
    estimated_minutes = fields.Integer(default=45)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)


class LaundryDelivery(models.Model):
    _name = "aimaze.laundry.delivery"
    _description = "Laundry Pickup and Delivery"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    job_type = fields.Selection([("pickup", "Pickup"), ("delivery", "Delivery"), ("pickup_delivery", "Pickup and Delivery")], default="pickup")
    order_id = fields.Many2one("aimaze.laundry.order", required=True)
    partner_id = fields.Many2one("res.partner", required=True)
    address = fields.Char()
    pickup_datetime = fields.Datetime()
    delivery_datetime = fields.Datetime()
    driver_id = fields.Many2one("hr.employee")
    vehicle = fields.Char()
    zone_id = fields.Many2one("aimaze.laundry.delivery.zone")
    state = fields.Selection(
        [
            ("scheduled", "Scheduled"),
            ("assigned", "Assigned"),
            ("picked_up", "Picked Up"),
            ("failed_pickup", "Failed Pickup"),
            ("in_transit", "In Transit"),
            ("delivered", "Delivered"),
            ("failed_delivery", "Failed Delivery"),
            ("cancelled", "Cancelled"),
        ],
        default="scheduled",
        tracking=True,
    )
    proof_pickup = fields.Binary(attachment=True)
    proof_delivery = fields.Binary(attachment=True)
    signature_photo = fields.Binary(attachment=True)
    proof_receiver_name = fields.Char()
    delivery_charge = fields.Monetary(currency_field="currency_id")
    remarks = fields.Text()
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    company_id = fields.Many2one(related="branch_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.delivery") or "New"
        return super().create(vals_list)

    def action_assigned(self):
        self.write({"state": "assigned"})

    def action_picked_up(self):
        self.write({"state": "picked_up"})
        self.order_id._set_state("picked_up")

    def action_in_transit(self):
        self.write({"state": "in_transit"})
        self.order_id._set_state("out_for_delivery")

    def action_delivered(self):
        self.write({"state": "delivered", "delivery_datetime": fields.Datetime.now()})
        self.order_id._set_state("delivered")


class LaundryInventoryUsage(models.Model):
    _name = "aimaze.laundry.inventory.usage"
    _description = "Laundry Inventory and Consumable Usage"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    order_id = fields.Many2one("aimaze.laundry.order")
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    product_id = fields.Many2one("product.product", required=True)
    usage_type = fields.Selection(
        [
            ("detergent", "Detergent"),
            ("chemical", "Chemical"),
            ("bag", "Packaging Bag"),
            ("hanger", "Hanger"),
            ("tag", "Tag"),
            ("perfume", "Perfume"),
            ("other", "Other"),
        ],
        default="detergent",
    )
    quantity = fields.Float(default=1.0)
    uom_id = fields.Many2one("uom.uom", related="product_id.uom_id", readonly=True)
    cost_amount = fields.Monetary(currency_field="currency_id")
    stock_move_id = fields.Many2one("stock.move", readonly=True)
    company_id = fields.Many2one(related="branch_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.inventory.usage") or "New"
        return super().create(vals_list)

    def action_deduct_stock(self):
        for usage in self:
            if not usage.branch_id.stock_location_id:
                raise UserError(_("Configure a stock location on the branch before deducting consumables."))
            move = self.env["stock.move"].create(
                {
                    "name": usage.name,
                    "product_id": usage.product_id.id,
                    "product_uom_qty": usage.quantity,
                    "product_uom": usage.product_id.uom_id.id,
                    "location_id": usage.branch_id.stock_location_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "company_id": usage.company_id.id,
                }
            )
            move._action_confirm()
            move._action_done()
            usage.stock_move_id = move.id


class LaundryMachine(models.Model):
    _name = "aimaze.laundry.machine"
    _description = "Laundry Machine"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "branch_id, name"

    name = fields.Char(required=True, tracking=True)
    machine_type = fields.Selection(
        [("washer", "Washer"), ("dryer", "Dryer"), ("iron", "Iron"), ("boiler", "Boiler"), ("press", "Pressing Machine"), ("other", "Other")],
        required=True,
    )
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    capacity = fields.Char()
    status = fields.Selection([("available", "Available"), ("running", "Running"), ("maintenance", "Maintenance"), ("breakdown", "Breakdown")], default="available")
    last_maintenance_date = fields.Date()
    next_maintenance_date = fields.Date()
    running_hours = fields.Float()
    breakdown_log = fields.Text()
    repair_cost = fields.Monetary(currency_field="currency_id")
    spare_parts_used = fields.Text()
    downtime_hours = fields.Float()
    maintenance_equipment_id = fields.Many2one("maintenance.equipment")
    company_id = fields.Many2one(related="branch_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", store=True, readonly=True)


class LaundryStaffTask(models.Model):
    _name = "aimaze.laundry.staff.task"
    _description = "Laundry Staff Task and Productivity"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_time desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True)
    order_id = fields.Many2one("aimaze.laundry.order")
    process_stage = fields.Selection(selection=lambda self: self.env["aimaze.laundry.order"]._fields["state"].selection, required=True)
    start_time = fields.Datetime(default=fields.Datetime.now)
    end_time = fields.Datetime()
    quantity_handled = fields.Float()
    rewash_count = fields.Integer()
    qc_fail_count = fields.Integer()
    productivity_score = fields.Float(compute="_compute_productivity", store=True)
    incentive_eligible = fields.Boolean(compute="_compute_productivity", store=True)
    branch_id = fields.Many2one(related="order_id.branch_id", store=True, readonly=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, readonly=True)

    @api.depends("quantity_handled", "rewash_count", "qc_fail_count")
    def _compute_productivity(self):
        for task in self:
            task.productivity_score = max(task.quantity_handled - task.rewash_count * 2 - task.qc_fail_count * 3, 0.0)
            task.incentive_eligible = task.productivity_score >= 25


class LaundryQC(models.Model):
    _name = "aimaze.laundry.qc"
    _description = "Laundry Quality Control"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "qc_date desc, id desc"

    order_id = fields.Many2one("aimaze.laundry.order", required=True)
    line_id = fields.Many2one("aimaze.laundry.order.line")
    qc_staff_id = fields.Many2one("hr.employee")
    qc_date = fields.Datetime(default=fields.Datetime.now)
    result = fields.Selection([("pass", "Pass"), ("fail", "Fail"), ("rewash", "Rewash"), ("damage", "Damage"), ("missing", "Missing")], required=True)
    remarks = fields.Text()
    photo = fields.Binary(attachment=True)
    customer_approval_required = fields.Boolean()
    branch_id = fields.Many2one(related="order_id.branch_id", store=True, readonly=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, readonly=True)


class LaundryComplaint(models.Model):
    _name = "aimaze.laundry.complaint"
    _description = "Laundry Complaints and Claims"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    partner_id = fields.Many2one("res.partner", required=True)
    order_id = fields.Many2one("aimaze.laundry.order")
    complaint_type = fields.Selection(
        [("delay", "Delay"), ("damage", "Damage"), ("lost", "Lost Item"), ("wrong", "Wrong Item"), ("poor_cleaning", "Poor Cleaning"), ("billing", "Billing Issue"), ("other", "Other")],
        required=True,
    )
    priority = fields.Selection([("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")], default="normal")
    responsible_id = fields.Many2one("res.users")
    state = fields.Selection([("new", "New"), ("review", "Under Review"), ("approved", "Approved"), ("rejected", "Rejected"), ("compensation", "Compensation"), ("closed", "Closed")], default="new")
    compensation_amount = fields.Monetary(currency_field="currency_id")
    refund_amount = fields.Monetary(currency_field="currency_id")
    notes = fields.Text()
    attachment = fields.Binary(attachment=True)
    branch_id = fields.Many2one(related="order_id.branch_id", store=True, readonly=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.complaint") or "New"
        return super().create(vals_list)


class LaundryBarcodeScan(models.Model):
    _name = "aimaze.laundry.barcode.scan"
    _description = "Laundry Barcode / QR Scan"
    _order = "scan_date desc, id desc"

    scan_date = fields.Datetime(default=fields.Datetime.now)
    order_id = fields.Many2one("aimaze.laundry.order", required=True)
    line_id = fields.Many2one("aimaze.laundry.order.line")
    barcode = fields.Char()
    stage = fields.Selection(selection=lambda self: self.env["aimaze.laundry.order"]._fields["state"].selection)
    scan_type = fields.Selection([("barcode", "Barcode"), ("qr", "QR"), ("manual", "Manual")], default="manual")
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    remarks = fields.Char()


class LaundryPaymentMethod(models.Model):
    _name = "aimaze.laundry.payment.method"
    _description = "Laundry Payment Method"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    journal_id = fields.Many2one("account.journal")
    method_type = fields.Selection([("cash", "Cash"), ("card", "Card"), ("bank", "Bank Transfer"), ("cheque", "Cheque"), ("online", "Online Payment")], default="cash")
    active = fields.Boolean(default=True)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    aimaze_laundry_order_id = fields.Many2one("aimaze.laundry.order", string="Laundry Order", index=True, ondelete="set null")
    laundry_is_advance = fields.Boolean(string="Laundry Advance")


class AccountMove(models.Model):
    _inherit = "account.move"

    laundry_order_id = fields.Many2one("aimaze.laundry.order", string="Laundry Order", index=True, ondelete="set null")
    laundry_contract_id = fields.Many2one("aimaze.laundry.contract", string="Laundry Contract", index=True, ondelete="set null")
    laundry_branch_id = fields.Many2one("aimaze.laundry.branch", string="Laundry Branch", index=True, ondelete="set null")


class LaundryLoyaltyPlan(models.Model):
    _name = "aimaze.laundry.membership.plan"
    _description = "Laundry Membership Plan"

    name = fields.Char(required=True)
    price = fields.Monetary(currency_field="currency_id")
    discount_percent = fields.Float()
    points_multiplier = fields.Float(default=1.0)
    validity_days = fields.Integer(default=365)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    active = fields.Boolean(default=True)


class LaundryLoyaltyTransaction(models.Model):
    _name = "aimaze.laundry.loyalty.transaction"
    _description = "Laundry Loyalty Transaction"
    _order = "date desc, id desc"

    date = fields.Datetime(default=fields.Datetime.now)
    partner_id = fields.Many2one("res.partner", required=True)
    order_id = fields.Many2one("aimaze.laundry.order")
    transaction_type = fields.Selection([("earn", "Earn"), ("redeem", "Redeem"), ("adjust", "Adjustment"), ("referral", "Referral")], default="earn")
    points = fields.Float(required=True)
    notes = fields.Char()


class LaundryNotificationLog(models.Model):
    _name = "aimaze.laundry.notification.log"
    _description = "Laundry Notification Log"
    _order = "create_date desc"

    order_id = fields.Many2one("aimaze.laundry.order")
    partner_id = fields.Many2one("res.partner")
    channel = fields.Selection([("whatsapp", "WhatsApp"), ("sms", "SMS"), ("email", "Email")], required=True)
    template_code = fields.Selection(
        [
            ("order_confirmed", "Order Confirmed"),
            ("pickup_assigned", "Pickup Assigned"),
            ("order_ready", "Order Ready"),
            ("out_for_delivery", "Out for Delivery"),
            ("delivered", "Delivered"),
            ("payment_reminder", "Payment Reminder"),
        ],
        required=True,
    )
    recipient = fields.Char()
    message_body = fields.Text()
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")], default="draft")
    provider_response = fields.Text()


class LaundryCashClosing(models.Model):
    _name = "aimaze.laundry.cash.closing"
    _description = "Laundry Daily Cash Closing"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    cashier_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    cash_received = fields.Monetary(currency_field="currency_id")
    card_received = fields.Monetary(currency_field="currency_id")
    bank_received = fields.Monetary(currency_field="currency_id")
    expenses = fields.Monetary(currency_field="currency_id")
    expected_cash = fields.Monetary(currency_field="currency_id")
    counted_cash = fields.Monetary(currency_field="currency_id")
    difference = fields.Monetary(compute="_compute_difference", store=True, currency_field="currency_id")
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("posted", "Posted")], default="draft")
    company_id = fields.Many2one(related="branch_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", store=True, readonly=True)

    @api.depends("counted_cash", "expected_cash")
    def _compute_difference(self):
        for closing in self:
            closing.difference = closing.counted_cash - closing.expected_cash


class LaundryDashboard(models.TransientModel):
    _name = "aimaze.laundry.dashboard"
    _description = "Laundry Dashboard"

    @api.model
    def get_dashboard_data(self):
        Order = self.env["aimaze.laundry.order"]
        today = fields.Date.context_today(self)
        today_start = fields.Datetime.to_string(fields.Datetime.from_string(str(today)))
        domain_today = [("order_date", ">=", today_start)]
        return {
            "today_orders": Order.search_count(domain_today),
            "pending_orders": Order.search_count([("state", "not in", ("delivered", "paid", "cancelled"))]),
            "ready_orders": Order.search_count([("state", "=", "ready")]),
            "delivered_orders": Order.search_count([("state", "=", "delivered")]),
            "cancelled_orders": Order.search_count([("state", "=", "cancelled")]),
            "total_sales": sum(Order.search(domain_today).mapped("amount_total")),
            "advance_received": sum(Order.search(domain_today).mapped("advance_paid")),
            "outstanding_receivables": sum(Order.search([("payment_status", "!=", "paid")]).mapped("balance_amount")),
            "delayed_orders": Order.search_count([("expected_delivery_datetime", "<", fields.Datetime.now()), ("state", "not in", ("delivered", "paid", "cancelled"))]),
            "complaints": self.env["aimaze.laundry.complaint"].search_count([("state", "!=", "closed")]),
            "rewash_cases": self.env["aimaze.laundry.qc"].search_count([("result", "=", "rewash")]),
            "low_stock_alerts": self.env["product.product"].search_count([("qty_available", "<=", 0), ("type", "=", "consu")]),
        }
