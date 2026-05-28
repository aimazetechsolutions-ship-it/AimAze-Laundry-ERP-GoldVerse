/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const actionRegistry = registry.category("actions");
const InteractiveAccountReport = actionRegistry.get("base_accounting_kit.interactive_account_report");

if (InteractiveAccountReport && !InteractiveAccountReport.prototype.__aimazeLedgerDrilldownPatch) {
    patch(InteractiveAccountReport.prototype, {
        __aimazeLedgerDrilldownPatch: true,

        hasLineActions(line) {
            if (this.reportKey === "general_ledger" && line.account_id && !line.move_id) {
                return true;
            }
            return super.hasLineActions(...arguments);
        },

        lineActions(line) {
            if (this.reportKey === "general_ledger" && line.account_id && !line.move_id) {
                return [{ key: "journal_entries", label: "View Journal Entry" }];
            }
            const actions = super.lineActions(...arguments);
            return actions.map((action) =>
                action.key === "journal_entry" ? { ...action, label: "View Journal Entry" } : action
            );
        },

        async runLineAction(line, actionKey, ev) {
            if (actionKey === "journal_entries" && line.account_id) {
                if (ev) {
                    ev.stopPropagation();
                    ev.preventDefault();
                }
                this.closeLineMenu();
                await this.action.doAction(this._aimazeJournalEntriesAction(line));
                return;
            }
            return super.runLineAction(...arguments);
        },

        _aimazeJournalEntriesAction(line) {
            const options = this.state.options || {};
            const domain = [["line_ids.account_id", "=", line.account_id]];

            if (options.date_from) {
                domain.push(["date", ">=", options.date_from]);
            }
            if (options.date_to) {
                domain.push(["date", "<=", options.date_to]);
            }
            if (options.target_move === "posted") {
                domain.push(["state", "=", "posted"]);
            }
            if (options.journal_ids && options.journal_ids.length) {
                domain.push(["journal_id", "in", options.journal_ids]);
            }

            return {
                type: "ir.actions.act_window",
                name: "View Journal Entry",
                res_model: "account.move",
                view_mode: "list,form",
                views: [[false, "list"], [false, "form"]],
                target: "current",
                domain,
                context: {
                    create: false,
                },
            };
        },
    });
}
