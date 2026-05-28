from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _aimaze_laundry_cleanup_app_switcher(self):
        """Keep the Laundry ERP app switcher clean after upgrades.

        Previous builds used the old ``laundry_management_pro`` namespace and
        some Odoo dependency apps still expose top-level roots. The dependencies
        remain installed and usable through AimAze Laundry ERP actions; only the
        duplicate top-level menu entries are hidden. Accounting is intentionally
        kept visible because Laundry uses the same accounting kit as Hospitality.
        """
        data_model = self.env["ir.model.data"].sudo()
        legacy_menu_ids = data_model.search([
            ("module", "=", "laundry_management_pro"),
            ("model", "=", "ir.ui.menu"),
        ]).mapped("res_id")

        accounting_menu = self.env.ref("account.menu_finance", raise_if_not_found=False)
        if accounting_menu:
            accounting_menu.sudo().write({
                "active": True,
                "name": "Accounting",
                "sequence": 60,
            })

        dependency_roots = [
            "contacts.menu_contacts",
            "crm.crm_menu_root",
            "sale.sale_menu_root",
            "point_of_sale.menu_point_root",
            "purchase.menu_purchase_root",
            "stock.menu_stock_root",
            "maintenance.menu_maintenance_title",
            "hr.menu_hr_root",
            "website.menu_website_configuration",
            "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
            "utm.menu_link_tracker_root",
        ]
        dependency_menu_ids = []
        for xmlid in dependency_roots:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                dependency_menu_ids.append(menu.id)

        menu_ids = set(legacy_menu_ids + dependency_menu_ids)
        if menu_ids:
            self.sudo().browse(menu_ids).write({"active": False})
        return True
