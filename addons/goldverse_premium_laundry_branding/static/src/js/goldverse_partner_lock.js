/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const PROTECTED_ITEMS = new Set([
    "archive",
    "unarchive",
    "delete",
    "duplicate",
]);

function applyLockClass(rootEl, locked) {
    if (!rootEl) return;
    rootEl.classList.toggle("gv-customer-locked-form", !!locked);
}

patch(FormController.prototype, {
    setup() {
        super.setup();
        useEffect(
            () => {
                if (this.props.resModel !== "res.partner") return;
                const locked = !!(
                    this.model.root &&
                    this.model.root.data &&
                    this.model.root.data.goldverse_partner_is_locked
                );
                const root = document.querySelector(".o_form_view") || document.querySelector(".o_form_renderer");
                applyLockClass(root, locked);
            },
            () => [
                this.props.resModel,
                this.model.root && this.model.root.data
                    ? this.model.root.data.goldverse_partner_is_locked
                    : null,
                this.model.root && this.model.root.resId,
            ]
        );
    },

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
