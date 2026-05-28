import json
import logging
import time

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class LaundrySaaSTenant(models.Model):
    _name = "aimaze.laundry.saas.tenant"
    _description = "AimAze Laundry ERP SaaS Tenant"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    tenant_code = fields.Char(required=True, tracking=True)
    domain = fields.Char()
    database_strategy = fields.Selection([("single_db", "Single Database"), ("multi_db", "Database Per Tenant")], default="single_db", required=True)
    primary_contact_id = fields.Many2one("res.partner")
    max_branches = fields.Integer(default=1)
    max_users = fields.Integer(default=10)
    state = fields.Selection([("draft", "Draft"), ("active", "Active"), ("suspended", "Suspended"), ("archived", "Archived")], default="draft", tracking=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _tenant_code_company_unique = models.Constraint("UNIQUE(tenant_code, company_id)", "Tenant code must be unique per company.")

    def action_activate(self):
        self.write({"state": "active"})

    def action_suspend(self):
        self.write({"state": "suspended"})


class LaundryIntegrationLog(models.Model):
    _name = "aimaze.laundry.integration.log"
    _description = "AimAze Laundry ERP Integration and API Log"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    log_type = fields.Selection(
        [
            ("api", "API"),
            ("notification", "Notification"),
            ("payment", "Payment"),
            ("delivery", "Delivery"),
            ("workflow", "Workflow"),
            ("backup", "Backup"),
            ("security", "Security"),
        ],
        required=True,
        default="api",
        index=True,
    )
    level = fields.Selection([("info", "Info"), ("warning", "Warning"), ("error", "Error"), ("critical", "Critical")], default="info", index=True)
    endpoint = fields.Char(index=True)
    method = fields.Char()
    request_payload = fields.Text()
    response_payload = fields.Text()
    status_code = fields.Integer()
    duration_ms = fields.Integer()
    error_message = fields.Text()
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    branch_id = fields.Many2one("aimaze.laundry.branch", index=True)
    order_id = fields.Many2one("aimaze.laundry.order", index=True)
    notification_id = fields.Many2one("aimaze.notification.queue")

    @api.model
    def log_event(self, name, log_type="api", level="info", payload=None, response=None, error=None, **extra):
        values = {
            "name": name,
            "log_type": log_type,
            "level": level,
            "request_payload": json.dumps(payload, default=str) if isinstance(payload, (dict, list)) else payload,
            "response_payload": json.dumps(response, default=str) if isinstance(response, (dict, list)) else response,
            "error_message": error,
        }
        values.update({key: value for key, value in extra.items() if value})
        _logger.log(logging.ERROR if level in ("error", "critical") else logging.INFO, "AimAze Laundry ERP %s: %s", log_type, name)
        return self.sudo().create(values)


class LaundryBackupConfig(models.Model):
    _name = "aimaze.laundry.backup.config"
    _description = "AimAze Laundry ERP Backup Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, name"

    name = fields.Char(required=True, default="Daily Backup")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    backup_database = fields.Boolean(default=True)
    backup_filestore = fields.Boolean(default=True)
    backup_path_placeholder = fields.Char(default="/var/backups/odoo")
    offsite_target_placeholder = fields.Char(string="Offsite Target Placeholder")
    retention_days = fields.Integer(default=30)
    last_backup_datetime = fields.Datetime()
    last_restore_test_datetime = fields.Datetime()
    state = fields.Selection([("draft", "Draft"), ("configured", "Configured"), ("paused", "Paused")], default="draft", tracking=True)
    notes = fields.Text()

    def action_mark_configured(self):
        self.write({"state": "configured"})

    def action_log_backup_placeholder(self):
        for config in self:
            self.env["aimaze.laundry.integration.log"].log_event(
                _("Backup placeholder executed"),
                log_type="backup",
                level="info",
                payload={"database": config.backup_database, "filestore": config.backup_filestore, "retention_days": config.retention_days},
                company_id=config.company_id.id,
            )
            config.last_backup_datetime = fields.Datetime.now()


class NotificationProvider(models.Model):
    _inherit = "aimaze.notification.provider"

    auth_type = fields.Selection([("none", "None"), ("bearer", "Bearer Token"), ("basic", "Basic Auth"), ("api_key", "API Key")], default="bearer")
    twilio_account_sid_placeholder = fields.Char()
    phone_number_id_placeholder = fields.Char(string="Meta Phone Number ID")
    api_version = fields.Char(default="v20.0")
    timeout_seconds = fields.Integer(default=20)
    retry_limit = fields.Integer(default=3)
    delivery_status_webhook = fields.Char()


class NotificationTemplate(models.Model):
    _inherit = "aimaze.notification.template"

    branch_id = fields.Many2one("aimaze.laundry.branch")
    channel = fields.Selection([("whatsapp", "WhatsApp"), ("sms", "SMS"), ("email", "Email"), ("auto", "Auto")], default="auto")


class NotificationQueue(models.Model):
    _inherit = "aimaze.notification.queue"

    retry_count = fields.Integer(default=0, index=True)
    max_retry = fields.Integer(default=3)
    next_retry_datetime = fields.Datetime(index=True)
    external_message_id = fields.Char(index=True)
    delivery_status = fields.Selection(
        [("unknown", "Unknown"), ("queued", "Queued"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed")],
        default="unknown",
        index=True,
    )
    last_attempt_datetime = fields.Datetime()
    provider_payload = fields.Text()

    def action_queue(self):
        self.write({"state": "queued", "delivery_status": "queued", "next_retry_datetime": fields.Datetime.now()})

    def action_retry(self):
        for queue in self:
            queue.write({"state": "queued", "delivery_status": "queued", "next_retry_datetime": fields.Datetime.now(), "error_message": False})

    def action_mark_failed(self):
        self.write({"state": "failed", "delivery_status": "failed", "last_attempt_datetime": fields.Datetime.now()})

    def _prepare_whatsapp_payload(self):
        self.ensure_one()
        return {
            "messaging_product": "whatsapp",
            "to": self.mobile,
            "type": "text",
            "text": {"body": self.message},
        }

    def process_queue(self, limit=50):
        now = fields.Datetime.now()
        queue_items = self.search(
            [
                ("state", "in", ("queued", "failed")),
                ("retry_count", "<", 10),
                "|",
                ("next_retry_datetime", "=", False),
                ("next_retry_datetime", "<=", now),
            ],
            limit=limit,
            order="create_date asc",
        )
        for item in queue_items:
            try:
                item._simulate_or_prepare_send()
            except Exception as exc:
                item._mark_retry_failure(str(exc))

    def _simulate_or_prepare_send(self):
        self.ensure_one()
        provider = self.provider_id or self.env["aimaze.notification.provider"].search(
            [("provider_type", "in", ("whatsapp", "sms", "email")), ("active", "=", True), ("company_id", "in", [False, self.company_id.id])],
            limit=1,
        )
        if not provider:
            self._mark_retry_failure(_("No active notification provider configured."))
            return False
        payload = self._prepare_whatsapp_payload() if provider.provider_type == "whatsapp" else {"to": self.mobile or self.email, "body": self.message}
        self.write(
            {
                "provider_id": provider.id,
                "provider_payload": json.dumps(payload, default=str),
                "last_attempt_datetime": fields.Datetime.now(),
                "retry_count": self.retry_count + 1,
                "state": "queued",
                "delivery_status": "queued",
                "error_message": _("Prepared for provider delivery. Add live connector credentials to send."),
            }
        )
        self.env["aimaze.laundry.integration.log"].log_event(
            _("Notification prepared"),
            log_type="notification",
            level="info",
            payload=payload,
            notification_id=self.id,
            company_id=self.company_id.id,
            branch_id=self.branch_id.id,
            order_id=self.order_id.id,
        )
        return True

    def _mark_retry_failure(self, error):
        self.ensure_one()
        retry_count = self.retry_count + 1
        max_retry = self.max_retry or (self.provider_id.retry_limit if self.provider_id else 3)
        values = {
            "retry_count": retry_count,
            "last_attempt_datetime": fields.Datetime.now(),
            "error_message": error,
            "delivery_status": "failed",
            "state": "failed" if retry_count >= max_retry else "queued",
            "next_retry_datetime": fields.Datetime.add(fields.Datetime.now(), minutes=min(60, 5 * retry_count)),
        }
        self.write(values)
        self.env["aimaze.laundry.integration.log"].log_event(
            _("Notification delivery failed"),
            log_type="notification",
            level="error",
            error=error,
            notification_id=self.id,
            company_id=self.company_id.id,
            branch_id=self.branch_id.id,
            order_id=self.order_id.id,
        )


class LaundryOrder(models.Model):
    _inherit = "aimaze.laundry.order"

    mobile_api_access_count = fields.Integer(default=0)
    last_mobile_access_datetime = fields.Datetime()

    def init(self):
        super().init()
        for table, columns in {
            "aimaze_laundry_order_line": ("order_id", "barcode", "tag_number", "branch_id", "company_id", "process_status"),
            "aimaze_laundry_barcode_scan": ("order_id", "line_id", "barcode", "stage", "branch_id", "scan_date"),
            "account_payment": ("aimaze_laundry_order_id", "laundry_is_advance", "company_id", "state"),
        }.items():
            for column in columns:
                self.env.cr.execute(
                    """
                    SELECT 1
                      FROM information_schema.columns
                     WHERE table_name = %s
                       AND column_name = %s
                    """,
                    (table, column),
                )
                if self.env.cr.fetchone():
                    self.env.cr.execute("CREATE INDEX IF NOT EXISTS %s_%s_phase4_idx ON %s (%s)" % (table, column, table, column))

    def _phase4_touch_mobile_access(self):
        self.write({"mobile_api_access_count": self.mobile_api_access_count + 1, "last_mobile_access_datetime": fields.Datetime.now()})


class LaundryDelivery(models.Model):
    _inherit = "aimaze.laundry.delivery"

    last_mobile_update_datetime = fields.Datetime()
    mobile_update_note = fields.Char()

    def action_mobile_update(self, state=False, cash_collected=False, note=False):
        vals = {"last_mobile_update_datetime": fields.Datetime.now(), "mobile_update_note": note}
        if cash_collected is not False:
            vals["cash_collected"] = cash_collected
            vals["driver_collection_state"] = "collected" if cash_collected else "not_collected"
        self.write(vals)
        if state == "picked_up":
            self.action_picked_up()
        elif state == "in_transit":
            self.action_in_transit()
        elif state == "delivered":
            self.action_delivered()
        elif state in ("failed_pickup", "failed_delivery", "cancelled"):
            self.write({"state": state})


class LaundryGarment(models.Model):
    _inherit = "aimaze.laundry.garment"

    last_mobile_scan_datetime = fields.Datetime()

    def action_mobile_stage_update(self, stage):
        self.action_set_stage(stage)
        self.write({"last_mobile_scan_datetime": fields.Datetime.now()})
