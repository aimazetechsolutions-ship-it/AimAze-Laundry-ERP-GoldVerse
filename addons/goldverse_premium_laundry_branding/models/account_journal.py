from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    code = fields.Char(size=None)
