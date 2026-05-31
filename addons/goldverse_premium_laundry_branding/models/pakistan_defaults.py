from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _goldverse_normalize_company_name(self):
        new_name = "GoldVerse Premium (Pvt.) Limited"
        legacy_name = "GoldVerse Premium Legacy Company"
        old_names = (
            "GoldVerse Premium Laundry",
            "GoldVerse Premium Laundry (Pvt) Limited",
            "GoldVerse Premium Laundry (Pvt.) Limited",
            "GoldVerse Premium (Pvt) Limited",
        )
        company_names = old_names + (new_name,)
        self.env.cr.execute(
            "SELECT id FROM res_company WHERE name IN %s ORDER BY id",
            (company_names,),
        )
        company_ids = [row[0] for row in self.env.cr.fetchall()]
        if not company_ids:
            return True

        primary_company_id = company_ids[0]
        self.env.cr.execute("SELECT to_regclass('aimaze_laundry_branch')")
        if self.env.cr.fetchone()[0]:
            self.env.cr.execute(
                """
                SELECT company_id
                  FROM aimaze_laundry_branch
                 WHERE company_id IN %s
                 LIMIT 1
                """,
                (tuple(company_ids),),
            )
            branch_company = self.env.cr.fetchone()
            if branch_company:
                primary_company_id = branch_company[0]

        for company_id in [item for item in company_ids if item != primary_company_id]:
            fallback_name = "%s %s" % (legacy_name, company_id)
            self.env.cr.execute("UPDATE res_company SET name = %s WHERE id = %s", (fallback_name, company_id))
            self.env.cr.execute(
                """
                UPDATE res_partner partner
                   SET name = %s,
                       commercial_company_name = %s
                  FROM res_company company
                 WHERE company.partner_id = partner.id
                   AND company.id = %s
                """,
                (fallback_name, fallback_name, company_id),
            )

        self.env.cr.execute("UPDATE res_company SET name = %s WHERE id = %s", (new_name, primary_company_id))
        self.env.cr.execute(
            """
            UPDATE res_partner partner
               SET name = %s,
                   commercial_company_name = %s
              FROM res_company company
             WHERE company.partner_id = partner.id
               AND company.id = %s
            """,
            (new_name, new_name, primary_company_id),
        )
        self.env.registry.clear_cache()
        return True

    def _goldverse_apply_pakistan_defaults(self):
        pakistan = self.env.ref("base.pk")
        pkr = self.env.ref("base.PKR")
        pkr.active = True

        companies = self or self.env["res.company"].search([])
        companies._goldverse_normalize_company_name()
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
