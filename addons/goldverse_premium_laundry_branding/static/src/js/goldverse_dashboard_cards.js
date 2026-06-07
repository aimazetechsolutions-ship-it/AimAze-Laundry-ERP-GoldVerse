/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormRenderer } from "@web/views/form/form_renderer";
import { onMounted, onWillUnmount } from "@odoo/owl";

function isGoldverseDashboardRenderer(renderer) {
    return renderer.props?.record?.resModel === "aimaze.laundry.executive.dashboard";
}

if (FormRenderer.prototype.__goldverseDashboardCardPatchVersion !== 1) {
    patch(FormRenderer.prototype, {
        __goldverseDashboardCardPatchVersion: 1,

        setup() {
            super.setup(...arguments);
            this.goldverseDashboardOrm = useService("orm");
            this.goldverseDashboardAction = useService("action");
            this.goldverseDashboardCardClick = async (ev) => {
                if (!isGoldverseDashboardRenderer(this)) {
                    return;
                }
                const card = ev.target.closest("[data-gv-dashboard-card]");
                if (!card || !card.closest(".goldverse-command-view")) {
                    return;
                }
                const cardKey = card.dataset.gvDashboardCard;
                const recordId = this.props.record?.resId;
                if (!cardKey || !recordId) {
                    return;
                }
                ev.preventDefault();
                ev.stopPropagation();
                const action = await this.goldverseDashboardOrm.call(
                    "aimaze.laundry.executive.dashboard",
                    "action_goldverse_open_dashboard_card",
                    [[recordId]],
                    {
                        context: {
                            ...(this.props.record.context || {}),
                            goldverse_card: cardKey,
                        },
                    }
                );
                if (action) {
                    await this.goldverseDashboardAction.doAction(action);
                }
            };
            onMounted(() => document.addEventListener("click", this.goldverseDashboardCardClick));
            onWillUnmount(() => document.removeEventListener("click", this.goldverseDashboardCardClick));
        },
    });
}
