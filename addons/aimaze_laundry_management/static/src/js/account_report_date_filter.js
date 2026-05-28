/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";

const InteractiveAccountReport = registry.category("actions").get("base_accounting_kit.interactive_account_report");

const dateString = (date) => [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
].join("-");

const parseDate = (value) => {
    const fallback = new Date();
    if (!value) {
        return fallback;
    }
    const [year, month, day] = String(value).split("-").map((part) => Number(part));
    if (!year || !month || !day) {
        return fallback;
    }
    return new Date(year, month - 1, day);
};

const periodBounds = (period, anchorDate) => {
    const anchor = parseDate(anchorDate || dateString(new Date()));
    let start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    let end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    if (period === "quarter") {
        const quarterStart = Math.floor(anchor.getMonth() / 3) * 3;
        start = new Date(anchor.getFullYear(), quarterStart, 1);
        end = new Date(anchor.getFullYear(), quarterStart + 3, 0);
    } else if (period === "year") {
        start = new Date(anchor.getFullYear(), 0, 1);
        end = new Date(anchor.getFullYear(), 11, 31);
    }
    return {
        startDate: dateString(start),
        endDate: dateString(end),
    };
};

const compactDateRangeDisplay = (bounds) => {
    const shortMonthNames = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    const start = parseDate(bounds.startDate);
    const end = parseDate(bounds.endDate);
    const sameYear = start.getFullYear() === end.getFullYear();
    const startText = sameYear
        ? `${shortMonthNames[start.getMonth()]} ${start.getDate()}`
        : `${shortMonthNames[start.getMonth()]} ${start.getDate()}, ${start.getFullYear()}`;
    return `${startText} - ${shortMonthNames[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
};

if (InteractiveAccountReport && !InteractiveAccountReport.prototype.__aimazeDateFilterPatch) {
    patch(InteractiveAccountReport.prototype, {
        __aimazeDateFilterPatch: true,

        setup() {
            super.setup(...arguments);
            this.state.accountCustomDateOpen = false;
            if (["today", "mtd", "ytd"].includes(this.state.options.period)) {
                const anchor = this.state.options.anchor_date || this.state.options.date_to || dateString(new Date());
                const bounds = periodBounds("month", anchor);
                this.state.options = {
                    ...this.state.options,
                    period: "month",
                    anchor_date: anchor,
                    date_from: bounds.startDate,
                    date_to: bounds.endDate,
                };
                this.state.pendingDateFrom = bounds.startDate;
                this.state.pendingDateTo = bounds.endDate;
            }
        },

        get dateRangeButtonLabel() {
            if ((this.options.period || "month") === "custom") {
                return compactDateRangeDisplay(this.bounds);
            }
            return this.periodMenuLabel;
        },

        toggleDateMenu() {
            if (!this.state.dateMenuOpen) {
                this.prepareCustomRange();
            }
            this.state.accountCustomDateOpen = false;
            this.state.dateMenuOpen = !this.state.dateMenuOpen;
            this.state.journalMenuOpen = false;
        },

        openCustomDateEditor(ev) {
            if (ev) {
                ev.stopPropagation();
            }
            this.prepareCustomRange();
            this.state.accountCustomDateOpen = true;
            this.state.dateMenuOpen = true;
            this.state.journalMenuOpen = false;
        },

        backToPeriodMenu(ev) {
            if (ev) {
                ev.stopPropagation();
            }
            this.state.accountCustomDateOpen = false;
            this.state.dateMenuOpen = true;
        },

        cancelCustomRange() {
            this.state.accountCustomDateOpen = false;
            return super.cancelCustomRange(...arguments);
        },

        applyCustomRange() {
            this.state.accountCustomDateOpen = false;
            return super.applyCustomRange(...arguments);
        },
    });
}

if (!window.__aimazeAccountReportDropdownCloseBound) {
    window.__aimazeAccountReportDropdownCloseBound = true;

    document.addEventListener("click", (event) => {
        window.setTimeout(() => {
            const report = document.querySelector(".o_account_interactive_report");
            if (!report) {
                return;
            }
            const openDropdowns = Array.from(report.querySelectorAll(".o_account_filter_dropdown")).filter((dropdown) =>
                dropdown.querySelector(".o_account_period_menu, .o_account_custom_date_popover, .o_account_journal_menu")
            );
            if (!openDropdowns.length || openDropdowns.some((dropdown) => dropdown.contains(event.target))) {
                return;
            }
            for (const dropdown of openDropdowns) {
                const button = dropdown.querySelector(".o_account_filter_btn");
                if (button) {
                    button.click();
                }
            }
        }, 0);
    });
}
