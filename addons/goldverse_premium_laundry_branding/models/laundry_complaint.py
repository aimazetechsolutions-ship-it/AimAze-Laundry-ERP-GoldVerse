from odoo import _, api, fields, models
from odoo.exceptions import UserError


LOCKED_STATES = ("approved", "compensation", "closed", "rejected")
ADMIN_GROUP_XMLID = "aimaze_laundry_management.group_laundry_admin"


class LaundryComplaint(models.Model):
    _inherit = "aimaze.laundry.complaint"

    goldverse_responsible_ids = fields.Many2many(
        "res.users",
        "goldverse_complaint_responsible_rel",
        "complaint_id",
        "user_id",
        string="Responsible",
    )
    goldverse_is_locked = fields.Boolean(
        compute="_compute_goldverse_is_locked",
        help="True when the complaint is past 'Under Review' and the current user is not a Laundry Admin.",
    )

    @api.depends("state")
    def _compute_goldverse_is_locked(self):
        is_admin = self.env.user.has_group(ADMIN_GROUP_XMLID)
        for rec in self:
            rec.goldverse_is_locked = (not is_admin) and rec.state in LOCKED_STATES

    def write(self, vals):
        if not self.env.user.has_group(ADMIN_GROUP_XMLID):
            non_state_vals = {k: v for k, v in vals.items() if k not in ("state", "goldverse_is_locked")}
            if non_state_vals:
                for rec in self:
                    if rec.state in LOCKED_STATES:
                        raise UserError(_(
                            "Complaint %s is %s. Only a Laundry Admin can edit it now."
                        ) % (rec.name or "", dict(self._fields["state"].selection).get(rec.state, rec.state)))
        return super().write(vals)

    def action_goldverse_close_complaint(self):
        for rec in self:
            if rec.state not in ("compensation", "approved"):
                raise UserError(_(
                    "Only complaints in Compensation or Approved state can be closed. Current state: %s."
                ) % dict(self._fields["state"].selection).get(rec.state, rec.state))
            rec.state = "closed"
            rec.message_post(body=_("Complaint closed by %s.") % self.env.user.name)
        return True
