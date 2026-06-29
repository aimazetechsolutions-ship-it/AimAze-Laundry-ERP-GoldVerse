/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

patch(FormController.prototype, {
    setup() {
        super.setup();
        useEffect(
            () => {
                if (this.props.resModel !== "aimaze.laundry.executive.dashboard") {
                    return;
                }
                const isExec = !!(
                    this.model.root &&
                    this.model.root.data &&
                    this.model.root.data.goldverse_is_executive_view
                );
                document.body.classList.toggle("gv-dashboard-cashier", !isExec);
                document.body.classList.toggle("gv-dashboard-exec", isExec);
                return () => {
                    document.body.classList.remove("gv-dashboard-cashier", "gv-dashboard-exec");
                };
            },
            () => [
                this.props.resModel,
                this.model.root && this.model.root.data
                    ? this.model.root.data.goldverse_is_executive_view
                    : null,
            ]
        );
    },
});
