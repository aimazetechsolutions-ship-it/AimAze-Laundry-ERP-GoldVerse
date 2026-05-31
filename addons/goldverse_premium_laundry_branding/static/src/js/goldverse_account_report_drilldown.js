/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { download } from "@web/core/network/download";

const InteractiveAccountReport = registry.category("actions").get("base_accounting_kit.interactive_account_report");

if (!window.__goldverseLedgerJournalEntryNavigation) {
    window.__goldverseLedgerJournalEntryNavigation = true;
    document.addEventListener("click", (ev) => {
        const button = ev.target.closest(".goldverse-ledger-view-journal-entry");
        if (!button) {
            return;
        }
        const action = button.closest("form")?.getAttribute("action");
        if (action) {
            ev.preventDefault();
            ev.stopPropagation();
            window.location.assign(action);
        }
    });
}

const accountIdsFromDomain = (domain) => {
    const ids = [];
    for (const item of domain || []) {
        if (!Array.isArray(item) || item[0] !== "account_id") {
            continue;
        }
        if (item[1] === "=" && item[2]) {
            ids.push(Number(item[2]));
        }
        if (item[1] === "in" && Array.isArray(item[2])) {
            ids.push(...item[2].map((value) => Number(value)).filter(Boolean));
        }
    }
    return ids;
};

const accountIdsFromLine = (line) => {
    const ids = accountIdsFromDomain(line?.action?.domain);
    const idMatch = String(line?.id || "").match(/(?:^|_)account_(\d+)/);
    if (idMatch) {
        ids.push(Number(idMatch[1]));
    }
    return [...new Set(ids.filter(Boolean))];
};

if (InteractiveAccountReport && InteractiveAccountReport.prototype.__goldverseAccountDrilldownPatchVersion !== 3) {
    patch(InteractiveAccountReport.prototype, {
        __goldverseAccountDrilldownPatch: true,
        __goldverseAccountDrilldownPatchVersion: 3,

        setup() {
            super.setup(...arguments);
            this.state.goldverseLineMenuId = null;
            this.state.goldverseMoveMenuId = null;
            const defaultOptions = this.props.action.context.default_options;
            if (defaultOptions) {
                this.state.options = { ...this.state.options, ...defaultOptions };
            }
            if (this.reportKey === "general_ledger") {
                this.state.searchTerm = this.state.searchTerm || "";
                this.state.options = {
                    ...this.state.options,
                    initial_balance: true,
                };
            }
        },

        get isGeneralLedgerReport() {
            return this.reportKey === "general_ledger";
        },

        get showLedgerSearch() {
            return this.isGeneralLedgerReport;
        },

        get showDisplayAccount() {
            return ["bank_book", "cash_book"].includes(this.reportKey);
        },

        get showInitialBalance() {
            return ["bank_book", "cash_book"].includes(this.reportKey);
        },

        get showSortBy() {
            return ["journal_audit", "bank_book", "cash_book"].includes(this.reportKey);
        },

        toggleGoldverseLineMenu(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            this.state.goldverseLineMenuId = this.state.goldverseLineMenuId === line.id ? null : line.id;
            this.state.goldverseMoveMenuId = null;
        },

        toggleGoldverseMoveMenu(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            this.state.goldverseMoveMenuId = this.state.goldverseMoveMenuId === line.id ? null : line.id;
            this.state.goldverseLineMenuId = null;
        },

        get visibleLines() {
            const lines = super.visibleLines;
            const term = String(this.state.searchTerm || "").trim().toLowerCase();
            if (!this.isGeneralLedgerReport || !term) {
                return lines;
            }
            const filtered = [];
            let activeAccountLine = null;
            let activeAccountMatched = false;
            for (const line of lines) {
                const values = Object.values(line.values || {}).join(" ");
                const matched = `${line.name || ""} ${values}`.toLowerCase().includes(term);
                if (line.type === "account") {
                    activeAccountLine = line;
                    activeAccountMatched = matched;
                    if (matched) {
                        filtered.push(line);
                    }
                    continue;
                }
                if (activeAccountMatched || matched) {
                    if (matched && activeAccountLine && !filtered.includes(activeAccountLine)) {
                        filtered.push(activeAccountLine);
                    }
                    filtered.push(line);
                }
            }
            return filtered;
        },

        setSearchTerm(value) {
            this.state.searchTerm = value || "";
        },

        closeGoldverseMoveMenus() {
            document
                .querySelectorAll(".goldverse-ledger-move-name.goldverse-move-menu-open")
                .forEach((cell) => cell.classList.remove("goldverse-move-menu-open"));
        },

        onGoldverseLedgerDocumentClick(ev) {
            if (!this.isGeneralLedgerReport) {
                return;
            }
            const target = ev.target;
            const journalEntryButton = target.closest(".goldverse-ledger-view-journal-entry");
            if (journalEntryButton) {
                ev.stopPropagation();
                ev.preventDefault();
                const moveId = Number(journalEntryButton.dataset.moveId);
                this.closeGoldverseMoveMenus();
                if (moveId) {
                    void this.action.doAction({
                        type: "ir.actions.act_window",
                        name: "Journal Entry",
                        res_model: "account.move",
                        res_id: moveId,
                        view_mode: "form",
                        views: [[false, "form"]],
                        target: "current",
                    });
                }
                return;
            }
            const moveButton = target.closest(".goldverse-ledger-move-menu-button");
            if (moveButton) {
                ev.stopPropagation();
                ev.preventDefault();
                const cell = moveButton.closest(".goldverse-ledger-move-name");
                const wasOpen = cell?.classList.contains("goldverse-move-menu-open");
                this.closeGoldverseMoveMenus();
                if (cell && !wasOpen) {
                    cell.classList.add("goldverse-move-menu-open");
                }
                return;
            }
            if (!target.closest(".goldverse-ledger-move-menu")) {
                this.closeGoldverseMoveMenus();
            }
        },

        goldverseGeneralLedgerOptions(line) {
            const accountIds = accountIdsFromLine(line);
            const options = {
                ...this.state.options,
                display_account: accountIds.length ? "all" : (this.state.options.display_account || "movement"),
                initial_balance: true,
                account_ids: accountIds,
            };
            return options;
        },

        formatLedgerAmount(value) {
            return `${this.formatAmount(value)} ${this.report.currency_label}`;
        },

        async exportXlsx() {
            await download({
                url: "/goldverse/interactive_report/xlsx",
                data: {
                    report_key: this.reportKey,
                    options: JSON.stringify(this.state.options),
                },
            });
        },

        async openGoldverseJournalItems(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            if (line.action) {
                await this.action.doAction(line.action);
            }
        },

        async openGoldverseJournalEntry(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            this.state.goldverseMoveMenuId = null;
            if (line.move_action) {
                await this.action.doAction(line.move_action);
            }
        },

        isGoldverseAgedAmountClickable(line, column) {
            if (!this.isAgedPartnerReport || !line?.action || column?.type !== "number") {
                return false;
            }
            return Math.abs(Number((line.values || {})[column.key] || 0)) >= 0.005;
        },

        async openGoldverseAgedLedger(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            if (line.action) {
                await this.action.doAction(line.action);
            }
        },

        async openGoldverseGeneralLedger(line, ev) {
            if (ev) {
                ev.stopPropagation();
                ev.preventDefault();
            }
            this.state.goldverseLineMenuId = null;
            await this.action.doAction({
                type: "ir.actions.client",
                name: "General Ledger",
                tag: "base_accounting_kit.interactive_account_report",
                context: {
                    report_key: "general_ledger",
                    default_options: this.goldverseGeneralLedgerOptions(line),
                },
            });
        },
    });
}
