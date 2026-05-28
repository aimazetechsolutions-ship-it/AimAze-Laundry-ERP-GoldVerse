/** @odoo-module **/

import { Component } from "@odoo/owl";

export class AimazeKpiCard extends Component {}

AimazeKpiCard.template = "aimaze_laundry_management.AimazeKpiCard";
AimazeKpiCard.props = {
    label: { type: String, optional: true },
    value: { type: [String, Number], optional: true },
    tone: { type: String, optional: true },
    icon: { type: String, optional: true },
};
