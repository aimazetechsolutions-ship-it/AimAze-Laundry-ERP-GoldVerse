from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LaundryScanWizard(models.TransientModel):
    _name = "aimaze.laundry.scan.wizard"
    _description = "Laundry Barcode / RFID Scan Wizard"

    barcode = fields.Char(required=True, string="Barcode / RFID / Order")
    scan_target = fields.Selection([("auto", "Auto Detect"), ("garment", "Garment"), ("order", "Order"), ("delivery", "Delivery Package")], default="auto", required=True)
    scan_action = fields.Selection(
        [
            ("open", "Open Record"),
            ("sorted", "Mark Sorted"),
            ("washing", "Mark Washing"),
            ("drying", "Mark Drying"),
            ("ironing", "Mark Ironing"),
            ("qc", "Send to QC"),
            ("packing", "Mark Packed"),
            ("ready", "Mark Ready"),
            ("delivered", "Mark Delivered"),
        ],
        default="open",
        required=True,
    )
    remarks = fields.Char()
    garment_id = fields.Many2one("aimaze.laundry.garment", readonly=True)
    order_id = fields.Many2one("aimaze.laundry.order", readonly=True)
    delivery_id = fields.Many2one("aimaze.laundry.delivery", readonly=True)

    def action_scan(self):
        self.ensure_one()
        garment, order, delivery = self._find_scan_record()
        self.write({"garment_id": garment.id if garment else False, "order_id": order.id if order else False, "delivery_id": delivery.id if delivery else False})
        if self.scan_action != "open":
            self._apply_scan_action(garment, order, delivery)
        if garment:
            return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.garment", "res_id": garment.id, "view_mode": "form"}
        if order:
            return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.order", "res_id": order.id, "view_mode": "form"}
        if delivery:
            return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.delivery", "res_id": delivery.id, "view_mode": "form"}
        raise UserError(_("No garment, order, or delivery package found for %s.") % self.barcode)

    def _find_scan_record(self):
        Garment = self.env["aimaze.laundry.garment"]
        Order = self.env["aimaze.laundry.order"]
        Delivery = self.env["aimaze.laundry.delivery"]
        garment = order = delivery = False
        if self.scan_target in ("auto", "garment"):
            garment = Garment.search(["|", "|", ("barcode", "=", self.barcode), ("name", "=", self.barcode), ("rfid_tag_uid", "=", self.barcode)], limit=1)
            if garment:
                order = garment.order_id
        if not order and self.scan_target in ("auto", "order"):
            order = Order.search(["|", ("barcode", "=", self.barcode), ("name", "=", self.barcode)], limit=1)
        if self.scan_target in ("auto", "delivery"):
            delivery = Delivery.search(["|", ("name", "=", self.barcode), ("order_id.barcode", "=", self.barcode)], limit=1)
            if delivery and not order:
                order = delivery.order_id
        return garment, order, delivery

    def _apply_scan_action(self, garment, order, delivery):
        garment_stage_map = {
            "sorted": "sorted",
            "washing": "washing",
            "drying": "drying",
            "ironing": "ironing",
            "qc": "qc",
            "packing": "packing",
            "ready": "ready",
            "delivered": "delivered",
        }
        order_state_map = {
            "sorted": "sorting",
            "washing": "washing",
            "drying": "drying",
            "ironing": "ironing",
            "qc": "qc",
            "packing": "packing",
            "ready": "ready",
            "delivered": "delivered",
        }
        if garment and self.scan_action in garment_stage_map:
            garment.action_set_stage(garment_stage_map[self.scan_action])
        if order and self.scan_action in order_state_map:
            order._set_state(order_state_map[self.scan_action])
        if delivery and self.scan_action == "delivered":
            delivery.action_delivered()
        if order:
            self.env["aimaze.laundry.barcode.scan"].create(
                {
                    "order_id": order.id,
                    "line_id": garment.order_line_id.id if garment and garment.order_line_id else False,
                    "barcode": self.barcode,
                    "stage": order.state,
                    "scan_type": "barcode",
                    "branch_id": order.branch_id.id,
                    "remarks": self.remarks,
                }
            )


class LaundrySetupWizard(models.TransientModel):
    _name = "aimaze.laundry.setup.wizard"
    _description = "AimAze Laundry ERP Initial Setup Wizard"

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    country_id = fields.Many2one("res.country")
    currency_id = fields.Many2one("res.currency")
    branch_name = fields.Char(required=True, default="Main Branch")
    branch_code = fields.Char(required=True, default="MAIN")
    branch_phone = fields.Char()
    sale_journal_id = fields.Many2one("account.journal")
    cash_journal_id = fields.Many2one("account.journal")
    bank_journal_id = fields.Many2one("account.journal")
    default_tax_id = fields.Many2one("account.tax")
    advance_liability_account_id = fields.Many2one("account.account")
    wallet_liability_account_id = fields.Many2one("account.account")
    laundry_income_account_id = fields.Many2one("account.account")
    delivery_income_account_id = fields.Many2one("account.account")

    @api.onchange("currency_id")
    def _onchange_currency_id(self):
        if self.currency_id and not self.country_id:
            xml_id_by_currency = {
                "AED": "base.ae",
                "PKR": "base.pk",
            }
            xml_id = xml_id_by_currency.get(self.currency_id.name)
            if xml_id:
                self.country_id = self.env.ref(xml_id, raise_if_not_found=False)

    def action_apply_setup(self):
        self.ensure_one()
        company_vals = {}
        if self.country_id:
            company_vals["country_id"] = self.country_id.id
        elif self.currency_id:
            xml_id_by_currency = {
                "AED": "base.ae",
                "PKR": "base.pk",
            }
            xml_id = xml_id_by_currency.get(self.currency_id.name)
            country = self.env.ref(xml_id, raise_if_not_found=False) if xml_id else False
            if country:
                company_vals["country_id"] = country.id
        if self.currency_id:
            company_vals["currency_id"] = self.currency_id.id
        if company_vals:
            self.company_id.write(company_vals)
        branch = self.env["aimaze.laundry.branch"].search([("company_id", "=", self.company_id.id), ("code", "=", self.branch_code)], limit=1)
        branch_vals = {
            "name": self.branch_name,
            "code": self.branch_code,
            "company_id": self.company_id.id,
            "phone": self.branch_phone,
            "sale_journal_id": self.sale_journal_id.id,
            "cash_journal_id": self.cash_journal_id.id,
            "bank_journal_id": self.bank_journal_id.id,
        }
        if branch:
            branch.write(branch_vals)
        else:
            branch = self.env["aimaze.laundry.branch"].create(branch_vals)
        config = self.env["aimaze.laundry.account.config"].get_config(self.company_id)
        config_vals = {
            "company_id": self.company_id.id,
            "advance_liability_account_id": self.advance_liability_account_id.id,
            "wallet_liability_account_id": self.wallet_liability_account_id.id,
            "laundry_income_account_id": self.laundry_income_account_id.id,
            "delivery_income_account_id": self.delivery_income_account_id.id,
            "cash_journal_id": self.cash_journal_id.id,
            "bank_journal_id": self.bank_journal_id.id,
            "default_tax_id": self.default_tax_id.id,
        }
        if config:
            config.write(config_vals)
        else:
            self.env["aimaze.laundry.account.config"].create(config_vals)
        return {"type": "ir.actions.act_window", "res_model": "aimaze.laundry.branch", "res_id": branch.id, "view_mode": "form"}
