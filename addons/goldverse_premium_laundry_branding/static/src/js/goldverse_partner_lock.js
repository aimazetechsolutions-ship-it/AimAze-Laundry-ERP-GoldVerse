/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

const PROTECTED_ITEMS = new Set([
    "archive",
    "unarchive",
    "delete",
    "duplicate",
]);

patch(FormController.prototype, {
    getStaticActionMenuItems() {
        const items = super.getStaticActionMenuItems(...arguments);
        try {
            if (this.props.resModel !== "res.partner") {
                return items;
            }
            const record = this.model.root;
            const isLocked = record && record.data && record.data.goldverse_partner_is_locked;
            if (!isLocked) {
                return items;
            }
            const filtered = {};
            for (const [key, value] of Object.entries(items || {})) {
                if (PROTECTED_ITEMS.has(key)) {
                    continue;
                }
                filtered[key] = value;
            }
            return filtered;
        } catch (e) {
            return items;
        }
    },
});
