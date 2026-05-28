from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


GARMENT_STAGE_SELECTION = [
    ("received", "Received"),
    ("sorted", "Sorted"),
    ("washing", "Washing"),
    ("drying", "Drying"),
    ("ironing", "Ironing"),
    ("qc", "QC"),
    ("rewash", "Rewash"),
    ("packing", "Packing"),
    ("ready", "Ready"),
    ("delivered", "Delivered"),
]


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

    garment_ids = fields.One2many("aimaze.laundry.garment", "order_id", string="Garments")
    wallet_transaction_ids = fields.One2many("aimaze.customer.wallet.transaction", "order_id", string="Wallet Transactions")
    subscription_id = fields.Many2one("aimaze.laundry.subscription", string="Subscription Used")
    wallet_used_amount = fields.Monetary(compute="_compute_phase2_payment_info", store=True, currency_field="currency_id")
    net_balance_amount = fields.Monetary(compute="_compute_phase2_payment_info", store=True, currency_field="currency_id")
    notification_queue_count = fields.Integer(compute="_compute_phase2_counts")
    garment_count = fields.Integer(compute="_compute_phase2_counts")

    @api.depends("balance_amount", "wallet_transaction_ids.amount", "wallet_transaction_ids.state", "wallet_transaction_ids.transaction_type")
    def _compute_phase2_payment_info(self):
        for order in self:
            wallet_used = sum(order.wallet_transaction_ids.filtered(lambda tx: tx.state == "posted" and tx.transaction_type == "order_payment").mapped("amount"))
            order.wallet_used_amount = wallet_used
            order.net_balance_amount = max(order.balance_amount - wallet_used, 0.0)

    def _compute_phase2_counts(self):
        Queue = self.env["aimaze.notification.queue"]
        for order in self:
            order.garment_count = len(order.garment_ids)
            order.notification_queue_count = Queue.search_count([("order_id", "=", order.id)])

    def _set_state(self, state):
        result = super()._set_state(state)
        self._phase2_sync_garment_stage(state)
        self._phase2_queue_state_notification(state)
        return result

    def _phase2_sync_garment_stage(self, order_state):
        stage_map = {
            "received": "received",
            "sorting": "sorted",
            "washing": "washing",
            "drying": "drying",
            "ironing": "ironing",
            "qc": "qc",
            "packing": "packing",
            "ready": "ready",
            "delivered": "delivered",
        }
        garment_stage = stage_map.get(order_state)
        if not garment_stage:
            return
        for order in self:
            order.garment_ids.filtered(lambda garment: garment.current_stage != garment_stage).action_set_stage(garment_stage)

    def _phase2_queue_state_notification(self, order_state):
        event_map = {
            "confirmed": "order_confirmed",
            "picked_up": "pickup_assigned",
            "received": "order_received",
            "ready": "order_ready",
            "out_for_delivery": "out_for_delivery",
            "delivered": "delivered",
        }
        event_type = event_map.get(order_state)
        if not event_type:
            return
        Queue = self.env["aimaze.notification.queue"]
        for order in self:
            Queue.create_from_event(event_type, order)

    def action_mark_sorting(self):
        self._set_state("sorting")

    def action_start_drying(self):
        self._set_state("drying")

    def action_mark_packing(self):
        self._set_state("packing")

    def action_open_garments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Garments"),
            "res_model": "aimaze.laundry.garment",
            "view_mode": "list,form",
            "domain": [("order_id", "=", self.id)],
            "context": {"default_order_id": self.id, "default_customer_id": self.partner_id.id, "default_branch_id": self.branch_id.id},
        }

    def action_open_notification_queue(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Notification Queue"),
            "res_model": "aimaze.notification.queue",
            "view_mode": "list,form",
            "domain": [("order_id", "=", self.id)],
        }

    def action_create_invoice(self):
        action = super().action_create_invoice()
        for order in self.filtered("invoice_id"):
            order._phase2_post_invoice_note()
        return action

    def _phase2_post_invoice_note(self):
        self.ensure_one()
        if self.advance_paid or self.wallet_used_amount:
            self.invoice_id.message_post(
                body=_("Laundry order %s has advance/payment already collected: %s %s. Use Odoo payment matching/reconciliation to settle the invoice.")
                % (self.name, self.advance_paid + self.wallet_used_amount, self.currency_id.name)
            )

    def action_use_wallet(self):
        for order in self:
            wallet = self.env["aimaze.customer.wallet"].get_wallet(order.partner_id, order.company_id, order.currency_id)
            amount = min(wallet.balance, order.net_balance_amount or order.balance_amount)
            if amount <= 0:
                raise UserError(_("No available wallet balance or no order balance to settle."))
            tx = self.env["aimaze.customer.wallet.transaction"].create(
                {
                    "wallet_id": wallet.id,
                    "partner_id": order.partner_id.id,
                    "order_id": order.id,
                    "transaction_type": "order_payment",
                    "amount": amount,
                    "currency_id": order.currency_id.id,
                    "company_id": order.company_id.id,
                    "branch_id": order.branch_id.id,
                    "description": _("Wallet payment for %s") % order.name,
                }
            )
            tx.action_post()
            order.message_post(body=_("Wallet payment applied: %s %s") % (amount, order.currency_id.name))


class LaundryOrderLine(models.Model):
    _inherit = "aimaze.laundry.order.line"

    garment_ids = fields.One2many("aimaze.laundry.garment", "order_line_id", string="Garments")

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._create_missing_garments()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if "quantity" in vals:
            self._create_missing_garments()
        return result

    def _create_missing_garments(self):
        Garment = self.env["aimaze.laundry.garment"]
        for line in self.filtered("order_id"):
            target_qty = int(line.quantity or 0)
            target_qty = max(min(target_qty, 200), 0)
            missing = target_qty - len(line.garment_ids)
            for _index in range(missing):
                Garment.create(
                    {
                        "order_id": line.order_id.id,
                        "order_line_id": line.id,
                        "customer_id": line.order_id.partner_id.id,
                        "branch_id": line.order_id.branch_id.id,
                        "company_id": line.order_id.company_id.id,
                        "garment_type": line.garment_item or line.garment_category or line.name,
                        "color": line.color,
                        "brand": line.brand,
                        "condition_received": line.condition_before,
                        "stain_details": line.stain_details,
                        "damage_details": line.damage_details,
                        "special_instructions": line.special_instruction,
                    }
                )


class LaundryDelivery(models.Model):
    _inherit = "aimaze.laundry.delivery"

    failed_pickup_reason = fields.Text()
    failed_delivery_reason = fields.Text()
    delivery_otp = fields.Char(string="Delivery OTP Placeholder")
    cash_collected = fields.Monetary(currency_field="currency_id")
    driver_note = fields.Text()

    def action_failed_pickup(self):
        self.write({"state": "failed_pickup"})

    def action_failed_delivery(self):
        self.write({"state": "failed_delivery"})


class LaundryGarment(models.Model):
    _name = "aimaze.laundry.garment"
    _description = "Laundry Garment Lifecycle"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Garment UID", default="New", copy=False, readonly=True, tracking=True)
    order_id = fields.Many2one("aimaze.laundry.order", required=True, ondelete="cascade", tracking=True)
    order_line_id = fields.Many2one("aimaze.laundry.order.line", ondelete="set null")
    customer_id = fields.Many2one("res.partner", required=True, tracking=True)
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    barcode = fields.Char(copy=False, readonly=True)
    qr_code = fields.Char(string="QR Code")
    garment_type = fields.Char(required=True)
    color = fields.Char()
    brand = fields.Char()
    fabric_type = fields.Char()
    condition_received = fields.Text()
    stain_details = fields.Text()
    damage_details = fields.Text()
    special_instructions = fields.Text()
    photo_before = fields.Binary(attachment=True)
    photo_after = fields.Binary(attachment=True)
    current_stage = fields.Selection(GARMENT_STAGE_SELECTION, default="received", tracking=True, index=True)
    current_staff_id = fields.Many2one("hr.employee")
    current_location = fields.Char()
    lost_item = fields.Boolean(tracking=True)
    rewash_count = fields.Integer(default=0)
    qc_result = fields.Selection([("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail"), ("rewash", "Rewash"), ("damage", "Damage"), ("missing", "Missing")], default="pending")
    delivered = fields.Boolean()
    delivery_datetime = fields.Datetime()
    history_ids = fields.One2many("aimaze.laundry.garment.history", "garment_id")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.garment") or "New"
            vals.setdefault("barcode", vals.get("name"))
            vals.setdefault("qr_code", vals.get("name"))
        garments = super().create(vals_list)
        for garment in garments:
            if not garment.barcode:
                garment.barcode = garment.name
            garment._create_history(False, garment.current_stage, _("Garment created"))
        return garments

    def _create_history(self, previous_stage, new_stage, remarks=False):
        History = self.env["aimaze.laundry.garment.history"]
        for garment in self:
            History.create(
                {
                    "garment_id": garment.id,
                    "order_id": garment.order_id.id,
                    "previous_stage": previous_stage or False,
                    "new_stage": new_stage,
                    "staff_id": garment.current_staff_id.id,
                    "remarks": remarks,
                }
            )

    def action_set_stage(self, stage):
        valid_stages = {value for value, _label in GARMENT_STAGE_SELECTION}
        if stage not in valid_stages:
            raise ValidationError(_("Invalid garment stage: %s") % stage)
        for garment in self:
            previous = garment.current_stage
            vals = {"current_stage": stage}
            if stage == "rewash":
                vals["rewash_count"] = garment.rewash_count + 1
                vals["qc_result"] = "rewash"
            if stage == "delivered":
                vals.update({"delivered": True, "delivery_datetime": fields.Datetime.now()})
            garment.write(vals)
            garment._create_history(previous, stage)

    def action_mark_sorted(self):
        self.action_set_stage("sorted")

    def action_mark_washing(self):
        self.action_set_stage("washing")

    def action_mark_drying(self):
        self.action_set_stage("drying")

    def action_mark_ironing(self):
        self.action_set_stage("ironing")

    def action_send_qc(self):
        self.action_set_stage("qc")

    def action_mark_rewash(self):
        self.action_set_stage("rewash")

    def action_mark_packed(self):
        self.action_set_stage("packing")

    def action_mark_ready(self):
        self.action_set_stage("ready")

    def action_mark_delivered(self):
        self.action_set_stage("delivered")


class LaundryGarmentHistory(models.Model):
    _name = "aimaze.laundry.garment.history"
    _description = "Laundry Garment History"
    _order = "date desc, id desc"

    garment_id = fields.Many2one("aimaze.laundry.garment", required=True, ondelete="cascade")
    order_id = fields.Many2one("aimaze.laundry.order", required=True, ondelete="cascade")
    previous_stage = fields.Selection(GARMENT_STAGE_SELECTION)
    new_stage = fields.Selection(GARMENT_STAGE_SELECTION, required=True)
    staff_id = fields.Many2one("hr.employee")
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    remarks = fields.Char()
    branch_id = fields.Many2one(related="garment_id.branch_id", store=True, readonly=True)
    company_id = fields.Many2one(related="garment_id.company_id", store=True, readonly=True)


class NotificationProvider(models.Model):
    _name = "aimaze.notification.provider"
    _description = "AimAze Notification Provider"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "provider_type, name"

    name = fields.Char(required=True, tracking=True)
    provider_type = fields.Selection([("whatsapp", "WhatsApp"), ("sms", "SMS"), ("email", "Email")], required=True, tracking=True)
    api_url = fields.Char()
    api_token_placeholder = fields.Char(string="API Token Placeholder")
    sender_id = fields.Char()
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    active = fields.Boolean(default=True)


class NotificationTemplate(models.Model):
    _name = "aimaze.notification.template"
    _description = "AimAze Notification Template"
    _order = "event_type, name"

    name = fields.Char(required=True)
    event_type = fields.Selection(
        [
            ("order_confirmed", "Order Confirmed"),
            ("pickup_assigned", "Pickup Assigned"),
            ("order_received", "Order Received"),
            ("order_ready", "Order Ready"),
            ("out_for_delivery", "Out for Delivery"),
            ("delivered", "Delivered"),
            ("payment_reminder", "Payment Reminder"),
            ("complaint_received", "Complaint Received"),
            ("complaint_closed", "Complaint Closed"),
            ("wallet_topup", "Wallet Top-up"),
            ("subscription_expiry", "Subscription Expiry Reminder"),
        ],
        required=True,
    )
    message_body = fields.Text(required=True)
    language = fields.Char(default="en")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    def render_message(self, order=False, partner=False):
        self.ensure_one()
        partner = partner or (order.partner_id if order else False)
        values = {
            "customer": partner.display_name if partner else "",
            "order": order.name if order else "",
            "amount": "%.2f" % order.amount_total if order else "",
            "balance": "%.2f" % order.balance_amount if order else "",
            "currency": order.currency_id.name if order else "",
        }
        message = self.message_body
        for key, value in values.items():
            message = message.replace("{{%s}}" % key, value)
        return message


class NotificationQueue(models.Model):
    _name = "aimaze.notification.queue"
    _description = "AimAze Notification Queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one("res.partner", string="Customer")
    mobile = fields.Char()
    email = fields.Char()
    order_id = fields.Many2one("aimaze.laundry.order")
    template_id = fields.Many2one("aimaze.notification.template")
    provider_id = fields.Many2one("aimaze.notification.provider")
    event_type = fields.Selection(related="template_id.event_type", store=True, readonly=True)
    message = fields.Text(required=True)
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")], default="draft", tracking=True)
    error_message = fields.Text()
    sent_date = fields.Datetime()
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    branch_id = fields.Many2one(related="order_id.branch_id", store=True, readonly=True)

    @api.model
    def create_from_event(self, event_type, order):
        template = self.env["aimaze.notification.template"].search(
            [("event_type", "=", event_type), ("active", "=", True), ("company_id", "in", [False, order.company_id.id])],
            limit=1,
        )
        if not template:
            return False
        message = template.render_message(order=order)
        return self.create(
            {
                "partner_id": order.partner_id.id,
                "mobile": order.mobile or order.partner_id.phone,
                "email": order.email or order.partner_id.email,
                "order_id": order.id,
                "template_id": template.id,
                "message": message,
                "company_id": order.company_id.id,
            }
        )

    def action_queue(self):
        self.write({"state": "queued"})

    def action_mark_sent(self):
        self.write({"state": "sent", "sent_date": fields.Datetime.now(), "error_message": False})

    def action_mark_failed(self):
        self.write({"state": "failed"})


class CustomerWallet(models.Model):
    _name = "aimaze.customer.wallet"
    _description = "Customer Laundry Wallet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "partner_id"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    balance = fields.Monetary(compute="_compute_balance", store=True, currency_field="currency_id")
    transaction_ids = fields.One2many("aimaze.customer.wallet.transaction", "wallet_id")
    active = fields.Boolean(default=True)

    _partner_company_currency_unique = models.Constraint("UNIQUE(partner_id, company_id, currency_id)", "A customer can have only one active wallet per company and currency.")

    @api.depends("partner_id", "currency_id")
    def _compute_name(self):
        for wallet in self:
            wallet.name = "%s - %s" % (wallet.partner_id.display_name or _("Wallet"), wallet.currency_id.name or "")

    @api.depends("transaction_ids.amount", "transaction_ids.transaction_type", "transaction_ids.state")
    def _compute_balance(self):
        credit_types = {"topup", "adjustment"}
        debit_types = {"order_payment", "refund", "expiry"}
        for wallet in self:
            balance = 0.0
            for tx in wallet.transaction_ids.filtered(lambda t: t.state == "posted"):
                if tx.transaction_type in credit_types:
                    balance += tx.amount
                elif tx.transaction_type in debit_types:
                    balance -= tx.amount
            wallet.balance = balance
            wallet.partner_id.laundry_wallet_balance = balance

    @api.model
    def get_wallet(self, partner, company, currency):
        wallet = self.search([("partner_id", "=", partner.id), ("company_id", "=", company.id), ("currency_id", "=", currency.id)], limit=1)
        if wallet:
            return wallet
        return self.create({"partner_id": partner.id, "company_id": company.id, "currency_id": currency.id, "branch_id": partner.laundry_branch_id.id})


class CustomerWalletTransaction(models.Model):
    _name = "aimaze.customer.wallet.transaction"
    _description = "Customer Laundry Wallet Transaction"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    wallet_id = fields.Many2one("aimaze.customer.wallet", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", required=True)
    order_id = fields.Many2one("aimaze.laundry.order")
    transaction_type = fields.Selection([("topup", "Top-up"), ("order_payment", "Order Payment"), ("refund", "Refund"), ("adjustment", "Adjustment"), ("expiry", "Expiry")], required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    journal_id = fields.Many2one("account.journal")
    account_move_id = fields.Many2one("account.move", readonly=True)
    date = fields.Date(default=fields.Date.context_today)
    description = fields.Char()
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted"), ("cancelled", "Cancelled")], default="draft", tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.customer.wallet.transaction") or "New"
        return super().create(vals_list)

    def action_post(self):
        for tx in self:
            if tx.amount <= 0:
                raise UserError(_("Wallet transaction amount must be greater than zero."))
            if tx.state != "posted":
                move = tx._create_account_move()
                tx.write({"state": "posted", "account_move_id": move.id if move else False})
                if tx.transaction_type == "topup":
                    self.env["aimaze.notification.queue"].create_from_wallet_event("wallet_topup", tx)

    def _create_account_move(self):
        self.ensure_one()
        config = self.env["aimaze.laundry.account.config"].get_config(self.company_id)
        if not config:
            return False
        journal = self.journal_id or config.cash_journal_id or config.bank_journal_id
        liquidity_account = journal.default_account_id if journal else False
        wallet_account = config.wallet_liability_account_id
        receivable_account = self.partner_id.property_account_receivable_id
        if self.transaction_type == "topup" and journal and liquidity_account and wallet_account:
            lines = [
                (0, 0, {"name": self.name, "account_id": liquidity_account.id, "partner_id": self.partner_id.id, "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": self.name, "account_id": wallet_account.id, "partner_id": self.partner_id.id, "debit": 0.0, "credit": self.amount}),
            ]
        elif self.transaction_type == "order_payment" and wallet_account and receivable_account:
            lines = [
                (0, 0, {"name": self.name, "account_id": wallet_account.id, "partner_id": self.partner_id.id, "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": self.name, "account_id": receivable_account.id, "partner_id": self.partner_id.id, "debit": 0.0, "credit": self.amount}),
            ]
        elif self.transaction_type == "refund" and journal and liquidity_account and wallet_account:
            lines = [
                (0, 0, {"name": self.name, "account_id": wallet_account.id, "partner_id": self.partner_id.id, "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": self.name, "account_id": liquidity_account.id, "partner_id": self.partner_id.id, "debit": 0.0, "credit": self.amount}),
            ]
        else:
            return False
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": self.date,
                "journal_id": journal.id,
                "company_id": self.company_id.id,
                "currency_id": self.currency_id.id,
                "ref": self.description or self.name,
                "line_ids": lines,
            }
        )
        move.action_post()
        return move

    def action_cancel(self):
        self.write({"state": "cancelled"})


class NotificationQueueWalletMixin(models.Model):
    _inherit = "aimaze.notification.queue"

    @api.model
    def create_from_wallet_event(self, event_type, wallet_transaction):
        template = self.env["aimaze.notification.template"].search(
            [("event_type", "=", event_type), ("active", "=", True), ("company_id", "in", [False, wallet_transaction.company_id.id])],
            limit=1,
        )
        if not template:
            return False
        message = template.message_body.replace("{{customer}}", wallet_transaction.partner_id.display_name).replace("{{amount}}", "%.2f" % wallet_transaction.amount).replace("{{currency}}", wallet_transaction.currency_id.name)
        return self.create(
            {
                "partner_id": wallet_transaction.partner_id.id,
                "mobile": wallet_transaction.partner_id.phone,
                "email": wallet_transaction.partner_id.email,
                "template_id": template.id,
                "message": message,
                "company_id": wallet_transaction.company_id.id,
            }
        )


class LaundrySubscriptionPackage(models.Model):
    _name = "aimaze.laundry.subscription.package"
    _description = "Laundry Subscription Package"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char(required=True, tracking=True)
    package_type = fields.Selection([("monthly_ironing", "Monthly Ironing"), ("family_wash", "Family Wash"), ("corporate_linen", "Corporate Linen"), ("fixed_value", "Fixed Value"), ("fixed_garment", "Fixed Garments"), ("fixed_kg", "Fixed Kg")], required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    price = fields.Monetary(required=True, currency_field="currency_id")
    included_value = fields.Monetary(currency_field="currency_id")
    included_quantity = fields.Float()
    validity_days = fields.Integer(default=30)
    active = fields.Boolean(default=True)


class LaundrySubscription(models.Model):
    _name = "aimaze.laundry.subscription"
    _description = "Customer Laundry Subscription"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    package_id = fields.Many2one("aimaze.laundry.subscription.package", required=True)
    company_id = fields.Many2one(related="package_id.company_id", store=True, readonly=True)
    branch_id = fields.Many2one(related="package_id.branch_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="package_id.currency_id", store=True, readonly=True)
    date_start = fields.Date(default=fields.Date.context_today, required=True)
    date_end = fields.Date(compute="_compute_date_end", store=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("expired", "Expired"), ("cancelled", "Cancelled")], default="draft", tracking=True)
    remaining_value = fields.Monetary(currency_field="currency_id")
    remaining_quantity = fields.Float()

    @api.depends("date_start", "package_id.validity_days")
    def _compute_date_end(self):
        for subscription in self:
            if subscription.date_start and subscription.package_id.validity_days:
                subscription.date_end = fields.Date.add(subscription.date_start, days=subscription.package_id.validity_days)
            else:
                subscription.date_end = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("aimaze.laundry.subscription") or "New"
        subscriptions = super().create(vals_list)
        for subscription in subscriptions:
            subscription.remaining_value = subscription.package_id.included_value
            subscription.remaining_quantity = subscription.package_id.included_quantity
        return subscriptions

    def action_activate(self):
        self.write({"state": "active"})

    def action_cancel(self):
        self.write({"state": "cancelled"})


class LaundryAccountConfig(models.Model):
    _name = "aimaze.laundry.account.config"
    _description = "Laundry Accounting Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "company_id"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    advance_liability_account_id = fields.Many2one("account.account", string="Advance Liability Account")
    wallet_liability_account_id = fields.Many2one("account.account", string="Wallet Liability Account")
    laundry_income_account_id = fields.Many2one("account.account", string="Laundry Income Account")
    delivery_income_account_id = fields.Many2one("account.account", string="Delivery Income Account")
    discount_account_id = fields.Many2one("account.account", string="Discount Account")
    compensation_expense_account_id = fields.Many2one("account.account", string="Compensation Expense Account")
    cash_journal_id = fields.Many2one("account.journal", domain="[('type','=','cash'), ('company_id','=', company_id)]")
    bank_journal_id = fields.Many2one("account.journal", domain="[('type','=','bank'), ('company_id','=', company_id)]")
    card_journal_id = fields.Many2one("account.journal", domain="[('type','in',('bank','cash')), ('company_id','=', company_id)]")
    default_tax_id = fields.Many2one("account.tax", domain="[('company_id','=', company_id)]")
    uae_vat_tax_id = fields.Many2one("account.tax", string="UAE VAT Tax", domain="[('company_id','=', company_id)]")
    pakistan_tax_id = fields.Many2one("account.tax", string="Pakistan Tax", domain="[('company_id','=', company_id)]")

    _company_unique = models.Constraint("UNIQUE(company_id)", "Only one laundry accounting configuration is allowed per company.")

    @api.model
    def get_config(self, company):
        return self.search([("company_id", "=", company.id)], limit=1)


class LaundryBranchProfitability(models.Model):
    _name = "aimaze.laundry.branch.profitability"
    _description = "Laundry Branch Profitability"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, branch_id"

    name = fields.Char(compute="_compute_name", store=True)
    branch_id = fields.Many2one("aimaze.laundry.branch", required=True)
    company_id = fields.Many2one(related="branch_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="branch_id.currency_id", store=True, readonly=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.start_of(fields.Date.context_today(self), "month"))
    date_to = fields.Date(required=True, default=lambda self: fields.Date.end_of(fields.Date.context_today(self), "month"))
    revenue = fields.Monetary(currency_field="currency_id")
    discounts = fields.Monetary(currency_field="currency_id")
    tax = fields.Monetary(currency_field="currency_id")
    consumable_cost = fields.Monetary(currency_field="currency_id")
    staff_cost = fields.Monetary(currency_field="currency_id")
    delivery_cost = fields.Monetary(currency_field="currency_id")
    maintenance_cost = fields.Monetary(currency_field="currency_id")
    compensation_cost = fields.Monetary(currency_field="currency_id")
    gross_profit = fields.Monetary(compute="_compute_profit", store=True, currency_field="currency_id")
    net_profit = fields.Monetary(compute="_compute_profit", store=True, currency_field="currency_id")
    profit_margin = fields.Float(compute="_compute_profit", store=True)

    @api.depends("branch_id", "date_from", "date_to")
    def _compute_name(self):
        for report in self:
            report.name = "%s: %s - %s" % (report.branch_id.display_name or _("Branch Profitability"), report.date_from or "", report.date_to or "")

    @api.depends("revenue", "discounts", "tax", "consumable_cost", "staff_cost", "delivery_cost", "maintenance_cost", "compensation_cost")
    def _compute_profit(self):
        for report in self:
            direct_cost = report.consumable_cost + report.delivery_cost + report.maintenance_cost + report.compensation_cost
            report.gross_profit = report.revenue - report.discounts - direct_cost
            report.net_profit = report.gross_profit - report.staff_cost
            report.profit_margin = (report.net_profit / report.revenue * 100.0) if report.revenue else 0.0

    def action_compute_profitability(self):
        Order = self.env["aimaze.laundry.order"]
        Usage = self.env["aimaze.laundry.inventory.usage"]
        Machine = self.env["aimaze.laundry.machine"]
        Complaint = self.env["aimaze.laundry.complaint"]
        for report in self:
            date_from = datetime.combine(report.date_from, time.min)
            date_to = datetime.combine(report.date_to, time.max)
            orders = Order.search([("branch_id", "=", report.branch_id.id), ("order_date", ">=", date_from), ("order_date", "<=", date_to), ("state", "not in", ("cancelled", "draft"))])
            usage = Usage.search([("branch_id", "=", report.branch_id.id), ("date", ">=", date_from), ("date", "<=", date_to)])
            machines = Machine.search([("branch_id", "=", report.branch_id.id)])
            complaints = Complaint.search([("branch_id", "=", report.branch_id.id), ("create_date", ">=", date_from), ("create_date", "<=", date_to)])
            report.write(
                {
                    "revenue": sum(orders.mapped("amount_total")),
                    "discounts": sum(orders.mapped("discount_amount")),
                    "tax": sum(orders.mapped("amount_tax")),
                    "consumable_cost": sum(usage.mapped("cost_amount")),
                    "delivery_cost": sum(orders.mapped("delivery_charge")),
                    "maintenance_cost": sum(machines.mapped("repair_cost")),
                    "compensation_cost": sum(complaints.mapped("compensation_amount")) + sum(complaints.mapped("refund_amount")),
                }
            )


class LaundryExecutiveDashboard(models.TransientModel):
    _name = "aimaze.laundry.executive.dashboard"
    _description = "Laundry Executive Dashboard"

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    branch_id = fields.Many2one("aimaze.laundry.branch")
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)

    def action_open_orders(self):
        return self.env.ref("aimaze_laundry_management.action_laundry_order").read()[0]
