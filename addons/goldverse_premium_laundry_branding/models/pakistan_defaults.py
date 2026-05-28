from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _goldverse_apply_pakistan_defaults(self):
        pakistan = self.env.ref("base.pk")
        pkr = self.env.ref("base.PKR")
        pkr.active = True

        companies = self or self.env["res.company"].search([])
        companies.write({
            "country_id": pakistan.id,
            "account_fiscal_country_id": pakistan.id,
            "currency_id": pkr.id,
        })
        companies.mapped("partner_id").write({"country_id": pakistan.id})
        self.env["res.users"].search([]).write({"tz": "Asia/Karachi"})

        chart_template = self.env["account.chart.template"]
        AccountMove = self.env["account.move"]
        for company in companies:
            has_posted_moves = AccountMove.search_count([
                ("company_id", "=", company.id),
                ("state", "=", "posted"),
            ])
            if company.chart_template != "pk" and not has_posted_moves:
                chart_template.try_loading("pk", company=company, install_demo=False)
        return True
