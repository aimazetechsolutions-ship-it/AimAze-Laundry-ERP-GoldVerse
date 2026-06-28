from odoo import fields, models


class LaundryComplaint(models.Model):
    _inherit = "aimaze.laundry.complaint"

    goldverse_responsible_ids = fields.Many2many(
        "res.users",
        "goldverse_complaint_responsible_rel",
        "complaint_id",
        "user_id",
        string="Responsible",
    )
