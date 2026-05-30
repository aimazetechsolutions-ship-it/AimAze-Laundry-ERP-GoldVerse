from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GoldVerseRoleAccessManager(models.Model):
    _name = "goldverse.role.access.manager"
    _description = "GoldVerse Role Access Manager"
    _order = "name"

    name = fields.Char(string="Role Name", required=True)
    group_id = fields.Many2one("res.groups", string="Existing Role", ondelete="set null")
    privilege_id = fields.Many2one(
        "res.groups.privilege",
        string="Privilege",
        required=True,
        default=lambda self: self._default_privilege_id(),
    )
    user_ids = fields.Many2many(
        "res.users",
        "goldverse_role_access_manager_user_rel",
        "manager_id",
        "user_id",
        string="Users",
    )
    module_menu_ids = fields.Many2many(
        "ir.ui.menu",
        "goldverse_role_access_manager_module_menu_rel",
        "manager_id",
        "menu_id",
        string="Module Menus",
        domain=[("parent_id", "=", False), ("active", "=", True)],
    )
    menu_ids = fields.Many2many(
        "ir.ui.menu",
        "goldverse_role_access_manager_menu_rel",
        "manager_id",
        "menu_id",
        string="Specific Menus",
        domain=[("active", "=", True)],
    )
    access_line_ids = fields.One2many(
        "goldverse.role.access.line",
        "manager_id",
        string="Access Rights",
    )
    note = fields.Text(
        default="Use this screen to create a role, assign users, choose visible menus, and define model access rights.",
    )

    @api.model
    def _default_privilege_id(self):
        return self.env.ref("aimaze_laundry_management.privilege_aimaze_laundry", raise_if_not_found=False)

    @api.onchange("group_id")
    def _onchange_group_id(self):
        if self.group_id:
            self.name = self.group_id.name
            self.privilege_id = self.group_id.privilege_id or self.privilege_id

    def _expand_menus_with_parents(self, menus):
        expanded = self.env["ir.ui.menu"].sudo().browse()
        for menu in menus:
            current = menu
            while current:
                expanded |= current
                current = current.parent_id
        return expanded

    def _children_of_menus(self, menus):
        Menu = self.env["ir.ui.menu"].sudo()
        children = Menu.browse()
        remaining = menus
        while remaining:
            next_children = Menu.search([("parent_id", "in", remaining.ids), ("active", "=", True)])
            next_children -= children
            if not next_children:
                break
            children |= next_children
            remaining = next_children
        return children

    def action_add_module_menus(self):
        for manager in self:
            menus = manager.module_menu_ids | manager._children_of_menus(manager.module_menu_ids)
            manager.menu_ids = [(6, 0, (manager.menu_ids | menus).ids)]
        return True

    def action_load_role(self):
        Access = self.env["ir.model.access"].sudo().with_context(active_test=False)
        for manager in self:
            group = manager.group_id
            if not group:
                raise UserError(_("Please select an existing role to load."))
            access_lines = []
            for access in Access.search([("group_id", "=", group.id)], order="model_id"):
                access_lines.append(
                    (
                        0,
                        0,
                        {
                            "access_id": access.id,
                            "model_id": access.model_id.id,
                            "perm_read": access.perm_read,
                            "perm_write": access.perm_write,
                            "perm_create": access.perm_create,
                            "perm_unlink": access.perm_unlink,
                            "active": access.active,
                        },
                    )
                )
            manager.write(
                {
                    "name": group.name,
                    "privilege_id": group.privilege_id.id or manager.privilege_id.id,
                    "user_ids": [(6, 0, group.user_ids.ids)],
                    "module_menu_ids": [(6, 0, group.menu_access.filtered(lambda menu: not menu.parent_id).ids)],
                    "menu_ids": [(6, 0, group.menu_access.ids)],
                    "access_line_ids": [(5, 0, 0)] + access_lines,
                }
            )
        return True

    def action_apply_role_access(self):
        Group = self.env["res.groups"].sudo()
        Access = self.env["ir.model.access"].sudo().with_context(active_test=False)
        base_user_group = self.env.ref("base.group_user", raise_if_not_found=False)
        for manager in self:
            if not manager.name:
                raise UserError(_("Please enter a role name."))
            group = manager.group_id
            group_values = {
                "name": manager.name,
                "privilege_id": manager.privilege_id.id,
            }
            if base_user_group:
                group_values["implied_ids"] = [(4, base_user_group.id)]
            if group:
                group.write(group_values)
            else:
                group = Group.create(group_values)
                manager.group_id = group.id

            module_menus = manager.module_menu_ids | manager._children_of_menus(manager.module_menu_ids)
            all_menus = manager._expand_menus_with_parents(manager.menu_ids | module_menus)
            group.write(
                {
                    "user_ids": [(6, 0, manager.user_ids.ids)],
                    "menu_access": [(6, 0, all_menus.ids)],
                }
            )

            for line in manager.access_line_ids.filtered("model_id"):
                access = line.access_id or Access.search(
                    [("group_id", "=", group.id), ("model_id", "=", line.model_id.id)],
                    limit=1,
                )
                values = {
                    "name": f"{group.name}: {line.model_id.model}",
                    "model_id": line.model_id.id,
                    "group_id": group.id,
                    "perm_read": line.perm_read,
                    "perm_write": line.perm_write,
                    "perm_create": line.perm_create,
                    "perm_unlink": line.perm_unlink,
                    "active": line.active,
                }
                if access:
                    access.write(values)
                    line.access_id = access.id
                else:
                    line.access_id = Access.create(values).id

            manager.menu_ids = [(6, 0, all_menus.ids)]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Role access updated"),
                "message": _("Users, menus, and access rights have been applied."),
                "type": "success",
                "sticky": False,
            },
        }


class GoldVerseRoleAccessLine(models.Model):
    _name = "goldverse.role.access.line"
    _description = "GoldVerse Role Access Line"
    _order = "model_id"

    manager_id = fields.Many2one(
        "goldverse.role.access.manager",
        required=True,
        ondelete="cascade",
    )
    access_id = fields.Many2one("ir.model.access", string="Existing Access Rule", ondelete="set null")
    model_id = fields.Many2one("ir.model", string="Model", required=True, ondelete="cascade")
    perm_read = fields.Boolean(string="Read", default=True)
    perm_write = fields.Boolean(string="Write")
    perm_create = fields.Boolean(string="Create")
    perm_unlink = fields.Boolean(string="Delete")
    active = fields.Boolean(default=True)
