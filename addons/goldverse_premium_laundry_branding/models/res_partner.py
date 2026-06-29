import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


GOLDVERSE_PARTNER_ADMIN_GROUPS = (
    "aimaze_laundry_management.group_laundry_admin",
    "base.group_system",
)


GOLDVERSE_PARTNER_LOCKED_FIELDS = frozenset({
    "name",
    "display_name",
    "street",
    "street2",
    "city",
    "zip",
    "state_id",
    "country_id",
    "email",
    "phone",
    "mobile",
    "vat",
    "comment",
    "function",
    "title",
    "active",
    "image_1920",
    "image_1024",
    "image_512",
    "image_256",
    "image_128",
    "company_type",
    "is_company",
    "parent_id",
    "lang",
    "tz",
    "goldverse_customer_category",
    "laundry_customer_type",
    "goldverse_is_blocked",
    "goldverse_block_reason",
})


class ResPartner(models.Model):
    _inherit = "res.partner"

    _goldverse_b2b_laundry_types = {"b2b", "corporate", "hotel", "salon", "gym", "restaurant"}

    goldverse_partner_is_locked = fields.Boolean(
        compute="_compute_goldverse_partner_is_locked",
        help="True when this is a saved customer partner and the current user is not a Laundry Admin.",
    )
    goldverse_is_blocked = fields.Boolean(
        string="Customer Blocked",
        default=False,
        tracking=True,
        copy=False,
        help="When true, no new laundry orders can be booked for this customer. Only Laundry Admins can toggle this flag.",
    )
    goldverse_blocked_at = fields.Datetime(string="Blocked On", readonly=True, copy=False)
    goldverse_blocked_by = fields.Many2one("res.users", string="Blocked By", readonly=True, copy=False)
    goldverse_block_reason = fields.Char(string="Block Reason", copy=False)

    def action_goldverse_block_customer(self):
        if not self._goldverse_partner_is_admin():
            raise UserError(_("Only a Laundry Admin can block a customer."))
        for partner in self:
            partner.sudo().write({
                "goldverse_is_blocked": True,
                "goldverse_blocked_at": fields.Datetime.now(),
                "goldverse_blocked_by": self.env.user.id,
            })
            partner.message_post(body=_("Customer blocked by %s. No new laundry orders can be created.") % self.env.user.name)

    def action_goldverse_unblock_customer(self):
        if not self._goldverse_partner_is_admin():
            raise UserError(_("Only a Laundry Admin can unblock a customer."))
        for partner in self:
            partner.sudo().write({
                "goldverse_is_blocked": False,
                "goldverse_blocked_at": False,
                "goldverse_blocked_by": False,
                "goldverse_block_reason": False,
            })
            partner.message_post(body=_("Customer unblocked by %s.") % self.env.user.name)

    @api.depends("customer_rank")
    def _compute_goldverse_partner_is_locked(self):
        is_admin = self._goldverse_partner_is_admin()
        for partner in self:
            rank = partner.customer_rank or 0
            is_saved = isinstance(partner.id, int) and partner.id > 0
            partner.goldverse_partner_is_locked = (not is_admin) and is_saved and rank > 0

    @api.model
    def _goldverse_partner_is_admin(self):
        user = self.env.user
        if user._is_admin() or user._is_superuser():
            return True
        return any(user.has_group(xmlid) for xmlid in GOLDVERSE_PARTNER_ADMIN_GROUPS)

    def _goldverse_partner_block_edit(self, action_label):
        if self._goldverse_partner_is_admin():
            return
        for partner in self:
            is_saved = isinstance(partner.id, int) and partner.id > 0
            if (partner.customer_rank or 0) > 0 and is_saved:
                raise UserError(_(
                    "Customer '%s' is locked. Only a Laundry Admin can %s an existing customer."
                ) % (partner.display_name or partner.name or "", action_label))

    def unlink(self):
        self._goldverse_partner_block_edit(_("delete"))
        return super().unlink()

    def toggle_active(self):
        self._goldverse_partner_block_edit(_("archive / unarchive"))
        return super().toggle_active()

    mobile = fields.Char(string="Mobile")
    goldverse_customer_category = fields.Selection(
        [("b2c", "B2C"), ("b2b", "B2B")],
        string="Customer Type",
        default="b2c",
        required=True,
        tracking=True,
    )
    laundry_customer_type = fields.Selection(
        selection_add=[
            ("b2c", "B2C"),
            ("b2b", "B2B"),
        ],
        ondelete={
            "b2c": "set null",
            "b2b": "set null",
        },
    )

    def _goldverse_normalize_mobile(self, value):
        return re.sub(r"\D+", "", value or "")

    def _goldverse_clean_mobile_number(self, value):
        return self._goldverse_normalize_mobile(value) if value else value

    def _goldverse_prepare_mobile_vals(self, vals):
        if vals.get("mobile"):
            vals["mobile"] = self._goldverse_clean_mobile_number(vals["mobile"])
        if vals.get("phone"):
            vals["phone"] = self._goldverse_clean_mobile_number(vals["phone"])
        return vals

    def _goldverse_mobile_value(self):
        self.ensure_one()
        return self._goldverse_normalize_mobile(self.mobile or self.phone)

    @api.model
    def _goldverse_validate_mobile_digits(self, value, label=None):
        if not value:
            return True
        mobile = self._goldverse_normalize_mobile(value)
        if len(mobile) != 11:
            raise ValidationError(_("%s must be exactly 11 numeric digits.") % (label or _("Mobile")))
        return True

    def _goldverse_mobile_lookup_label(self):
        self.ensure_one()
        mobile = self._goldverse_mobile_value()
        name = self.name or self.display_name or ""
        return f"{mobile} - {name}" if mobile and name else mobile or name

    @api.depends_context(
        "show_address",
        "partner_show_db_id",
        "show_email",
        "show_vat",
        "lang",
        "formatted_display_name",
        "goldverse_mobile_lookup",
    )
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get("goldverse_mobile_lookup"):
            return
        for partner in self:
            partner.display_name = partner._goldverse_mobile_lookup_label()

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        if not self.env.context.get("goldverse_mobile_lookup"):
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        domain = list(domain or [])
        if name:
            cleaned_name = self._goldverse_normalize_mobile(name)
            terms = [
                ("name", operator, name),
                ("mobile", operator, name),
                ("phone", operator, name),
            ]
            if cleaned_name and cleaned_name != name:
                terms.extend([
                    ("mobile", operator, cleaned_name),
                    ("phone", operator, cleaned_name),
                ])
            search_domain = expression.OR([[term] for term in terms])
            domain = expression.AND([domain, search_domain])
        partners = self.search(domain, limit=limit)
        return [(partner.id, partner._goldverse_mobile_lookup_label()) for partner in partners.sudo()]

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if not self.env.context.get("goldverse_mobile_lookup"):
            return values
        mobile = (
            self.env.context.get("default_mobile")
            or self.env.context.get("default_phone")
            or self.env.context.get("default_name")
        )
        cleaned_mobile = self._goldverse_clean_mobile_number(mobile)
        if cleaned_mobile and len(cleaned_mobile) == 11:
            if "mobile" in fields_list:
                values.setdefault("mobile", cleaned_mobile)
            if "phone" in fields_list:
                values.setdefault("phone", cleaned_mobile)
            if values.get("name") == mobile:
                values["name"] = False
        return values

    @api.model
    def _goldverse_category_from_laundry_type(self, laundry_customer_type, is_company=False):
        if laundry_customer_type in self._goldverse_b2b_laundry_types or is_company:
            return "b2b"
        return "b2c"

    @api.model
    def _goldverse_prepare_customer_category_vals(self, vals):
        if vals.get("goldverse_customer_category"):
            vals["laundry_customer_type"] = vals["goldverse_customer_category"]
            if vals["goldverse_customer_category"] == "b2b":
                vals.setdefault("is_company", True)
                vals.setdefault("company_type", "company")
            elif vals["goldverse_customer_category"] == "b2c":
                vals.setdefault("is_company", False)
                vals.setdefault("company_type", "person")
            return vals

        if vals.get("laundry_customer_type"):
            vals["goldverse_customer_category"] = self._goldverse_category_from_laundry_type(
                vals["laundry_customer_type"],
                vals.get("is_company", False),
            )
            vals["laundry_customer_type"] = vals["goldverse_customer_category"]
            return vals

        if vals.get("customer_rank", 0) > 0:
            vals.setdefault("goldverse_customer_category", "b2c")
            vals.setdefault("laundry_customer_type", vals["goldverse_customer_category"])
        return vals

    @api.model
    def _goldverse_sync_customer_categories(self):
        partners = self.with_context(active_test=False).sudo().search([])
        for partner in partners:
            category = partner.goldverse_customer_category or self._goldverse_category_from_laundry_type(
                partner.laundry_customer_type,
                partner.is_company,
            )
            vals = {"goldverse_customer_category": category}
            if partner.customer_rank > 0 and partner.laundry_customer_type != category:
                vals["laundry_customer_type"] = category
            partner.with_context(goldverse_skip_customer_phone_required=True).write(vals)
        partners._goldverse_ensure_customer_rank_for_customer_categories()
        return True

    def _goldverse_customer_rank_candidates(self):
        company_partner_ids = set(self.env["res.company"].sudo().search([]).mapped("partner_id").ids)
        return self.filtered(
            lambda partner: partner.active
            and partner.customer_rank <= 0
            and partner.goldverse_customer_category in ("b2c", "b2b")
            and partner.id not in company_partner_ids
            and not partner.user_ids
            and bool(partner._goldverse_mobile_value())
        )

    def _goldverse_ensure_customer_rank_for_customer_categories(self):
        candidates = self.with_context(active_test=False)._goldverse_customer_rank_candidates()
        if candidates:
            candidates.with_context(goldverse_skip_customer_rank_sync=True).sudo().write({"customer_rank": 1})
        return True

    def _goldverse_check_duplicate_mobile(self):
        all_partners = self.with_context(active_test=False).sudo().search([("id", "not in", self.ids)])
        seen = {}
        for existing in all_partners:
            mobile = existing._goldverse_mobile_value()
            if mobile:
                seen[mobile] = existing
        for partner in self:
            mobile = partner._goldverse_mobile_value()
            if not mobile:
                continue
            duplicate = seen.get(mobile)
            if duplicate:
                raise ValidationError(
                    _("Mobile number %s is already used by customer %s.")
                    % (partner.mobile or partner.phone, duplicate.display_name)
                )
            seen[mobile] = partner

    def _goldverse_check_customer_phone_required(self):
        if self.env.context.get("goldverse_skip_customer_phone_required"):
            return True
        missing = self.filtered(lambda partner: partner.customer_rank > 0 and not partner._goldverse_mobile_value())
        if missing:
            names = ", ".join(missing.mapped("display_name")[:5])
            raise ValidationError(_("Phone is mandatory for customer(s): %s.") % names)
        invalid = self.filtered(lambda partner: partner.customer_rank > 0 and len(partner._goldverse_mobile_value()) != 11)
        if invalid:
            names = ", ".join(invalid.mapped("display_name")[:5])
            raise ValidationError(_("Phone/Mobile must be exactly 11 numeric digits for customer(s): %s.") % names)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        default_customer_rank = self.env.context.get("default_customer_rank")
        default_laundry_customer_type = self.env.context.get("default_laundry_customer_type")
        for vals in vals_list:
            self._goldverse_prepare_mobile_vals(vals)
            if default_customer_rank and not vals.get("customer_rank"):
                vals["customer_rank"] = default_customer_rank
            if default_laundry_customer_type and not vals.get("laundry_customer_type"):
                vals["laundry_customer_type"] = default_laundry_customer_type
            self._goldverse_prepare_customer_category_vals(vals)
        partners = super().create(vals_list)
        partners._goldverse_check_duplicate_mobile()
        partners._goldverse_check_customer_phone_required()
        partners._goldverse_ensure_customer_rank_for_customer_categories()
        return partners

    def write(self, vals):
        vals = dict(vals)
        if not self._goldverse_partner_is_admin():
            locked_keys = [k for k in vals.keys() if k in GOLDVERSE_PARTNER_LOCKED_FIELDS]
            if locked_keys:
                for partner in self:
                    is_saved = isinstance(partner.id, int) and partner.id > 0
                    if not (partner.customer_rank or 0) > 0 or not is_saved:
                        continue
                    changed_keys = []
                    for key in locked_keys:
                        new_val = vals.get(key)
                        current = partner[key]
                        if hasattr(current, "id"):
                            current = current.id
                        if hasattr(current, "ids"):
                            current = list(current.ids)
                        if new_val != current and not (new_val in (False, None, "") and current in (False, None, "")):
                            changed_keys.append(key)
                    if changed_keys:
                        raise UserError(_(
                            "Customer '%s' is locked. Only a Laundry Admin can edit, archive, or delete an existing customer.\n(Blocked fields: %s)"
                        ) % (partner.display_name or partner.name or "", ", ".join(sorted(changed_keys))))
        self._goldverse_prepare_mobile_vals(vals)
        self._goldverse_prepare_customer_category_vals(vals)
        result = super().write(vals)
        if {"phone", "mobile"} & set(vals):
            self._goldverse_check_duplicate_mobile()
        if {"customer_rank", "phone", "mobile", "goldverse_customer_category", "laundry_customer_type"} & set(vals):
            self._goldverse_check_customer_phone_required()
        if not self.env.context.get("goldverse_skip_customer_rank_sync") and {
            "goldverse_customer_category",
            "laundry_customer_type",
            "phone",
            "mobile",
            "active",
        } & set(vals):
            self._goldverse_ensure_customer_rank_for_customer_categories()
        return result
