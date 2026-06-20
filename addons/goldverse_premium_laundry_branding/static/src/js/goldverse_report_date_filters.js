/** @odoo-module **/

import { serializeDate, serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useState } from "@odoo/owl";

const { DateTime } = luxon;

const REPORT_FILTER_CONFIG = {
    "aimaze.laundry.order": { dateField: "order_date" },
    "aimaze.laundry.delivery": { dateField: "pickup_datetime" },
    "aimaze.laundry.inventory.usage": { dateField: "date" },
    "aimaze.laundry.staff.task": { dateField: "start_time" },
    "aimaze.laundry.branch.profitability": { dateField: "date_from" },
    "account.payment": { dateField: "date" },
    "account.move.line": { dateField: "date" },
    "aimaze.customer.wallet.transaction": { dateField: "date" },
};

const PERIOD_FILTER_NAMES = {
    today: "today",
    mtd: "gv_mtd",
    ytd: "gv_ytd",
    itd: "gv_itd",
    custom: "gv_custom_range",
};
const ALL_PERIOD_NAMES = Object.values(PERIOD_FILTER_NAMES);

const CUSTOMER_FILTER_NAMES = {
    all: "gv_all_customers",
    b2c: "gv_b2c",
    b2b: "gv_b2b",
};

function findSearchItemByName(searchModel, name) {
    if (!searchModel) {
        return null;
    }
    return Object.values(searchModel.searchItems || {}).find((item) => item.name === name) || null;
}

function isItemActive(searchModel, item) {
    if (!searchModel || !item) {
        return false;
    }
    return (searchModel.query || []).some((entry) => entry.searchItemId === item.id);
}

function deactivateFilter(searchModel, item, { silent = false } = {}) {
    if (!searchModel || !item) {
        return false;
    }
    const index = (searchModel.query || []).findIndex((entry) => entry.searchItemId === item.id);
    if (index === -1) {
        return false;
    }
    if (silent) {
        searchModel.query.splice(index, 1);
        return true;
    }
    searchModel.toggleSearchItem(item.id);
    return true;
}

function activateFilter(searchModel, item) {
    if (!searchModel || !item) {
        return;
    }
    if (!isItemActive(searchModel, item)) {
        searchModel.toggleSearchItem(item.id);
    }
}

function buildPeriodBounds(period) {
    const today = DateTime.local().startOf("day");
    if (period === "today") {
        return { from: today, to: today };
    }
    if (period === "mtd") {
        return { from: today.startOf("month"), to: today };
    }
    if (period === "ytd") {
        return { from: today.startOf("year"), to: today };
    }
    return null;
}

function buildDomainForRange(dateField, fieldType, fromDateTime, toDateTime) {
    if (!fromDateTime || !toDateTime) {
        return [];
    }
    if (fieldType === "datetime") {
        return [
            [dateField, ">=", serializeDateTime(fromDateTime.startOf("day"))],
            [dateField, "<=", serializeDateTime(toDateTime.endOf("day"))],
        ];
    }
    return [
        [dateField, ">=", serializeDate(fromDateTime.startOf("day"))],
        [dateField, "<=", serializeDate(toDateTime.startOf("day"))],
    ];
}

patch(SearchBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.goldverseToolbarState = useState({
            period: "today",
            customerType: "all",
            customOpen: false,
            customFrom: DateTime.local().toISODate(),
            customTo: DateTime.local().toISODate(),
        });
        useBus(this.env.searchModel, "update", () => this._goldverseSyncFromSearchModel());
        this._goldverseSyncFromSearchModel();
        this._goldverseBoundOutsideClick = (ev) => this._goldverseOnOutsideClick(ev);
        document.addEventListener("mousedown", this._goldverseBoundOutsideClick, true);
    },

    get goldverseReportConfig() {
        return REPORT_FILTER_CONFIG[this.env.searchModel?.resModel] || null;
    },

    get goldverseDateFieldType() {
        const config = this.goldverseReportConfig;
        if (!config) {
            return "datetime";
        }
        const fieldDef = this.env.searchModel?.searchViewFields?.[config.dateField];
        return fieldDef?.type || "datetime";
    },

    get isGoldverseReportToolbar() {
        if (!this.goldverseReportConfig || !this.env.searchModel) {
            return false;
        }
        return ALL_PERIOD_NAMES.every((name) => Boolean(findSearchItemByName(this.env.searchModel, name)));
    },

    get hasGoldverseCustomerFilters() {
        return Object.values(CUSTOMER_FILTER_NAMES).every((name) =>
            Boolean(findSearchItemByName(this.env.searchModel, name))
        );
    },

    goldversePeriodButtonClass(period) {
        const active = this.goldverseToolbarState.period === period;
        return `btn ${active ? "btn-primary" : "btn-secondary"}`;
    },

    goldverseCustomerButtonClass(customerType) {
        const active = (this.goldverseToolbarState.customerType || "all") === customerType;
        return `btn ${active ? "btn-primary" : "btn-secondary"}`;
    },

    _goldverseSyncFromSearchModel() {
        if (!this.isGoldverseReportToolbar) {
            return;
        }
        const searchModel = this.env.searchModel;
        let activePeriod = "today";
        for (const [period, name] of Object.entries(PERIOD_FILTER_NAMES)) {
            const item = findSearchItemByName(searchModel, name);
            if (isItemActive(searchModel, item)) {
                activePeriod = period;
                break;
            }
        }
        this.goldverseToolbarState.period = activePeriod;
        if (activePeriod !== "custom") {
            this.goldverseToolbarState.customOpen = false;
        }

        let activeCustomer = "all";
        for (const [customerType, name] of Object.entries(CUSTOMER_FILTER_NAMES)) {
            const item = findSearchItemByName(searchModel, name);
            if (isItemActive(searchModel, item)) {
                activeCustomer = customerType;
                break;
            }
        }
        this.goldverseToolbarState.customerType = activeCustomer;
    },

    _goldverseDeactivateAllPeriods({ silent = false } = {}) {
        const searchModel = this.env.searchModel;
        for (const name of ALL_PERIOD_NAMES) {
            deactivateFilter(searchModel, findSearchItemByName(searchModel, name), { silent });
        }
    },

    _goldverseDeactivateAllCustomers({ silent = false } = {}) {
        const searchModel = this.env.searchModel;
        for (const name of Object.values(CUSTOMER_FILTER_NAMES)) {
            deactivateFilter(searchModel, findSearchItemByName(searchModel, name), { silent });
        }
    },

    _goldverseForceNotify(searchModel) {
        if (typeof searchModel._notify === "function") {
            const result = searchModel._notify();
            if (result && typeof result.then === "function") {
                result.then(() => {}, () => {});
            }
            return;
        }
        if (typeof searchModel._reset === "function") {
            searchModel._reset();
        }
        searchModel.search();
    },

    goldverseSelectPeriod(period) {
        if (!this.isGoldverseReportToolbar) {
            return;
        }
        const searchModel = this.env.searchModel;
        if (period === "custom") {
            this.goldverseToolbarState.customOpen = !this.goldverseToolbarState.customOpen;
            return;
        }
        const targetItem = findSearchItemByName(searchModel, PERIOD_FILTER_NAMES[period]);
        if (!targetItem) {
            return;
        }
        // Reset the custom-range item's domain so a re-pick later starts clean.
        const customItem = findSearchItemByName(searchModel, PERIOD_FILTER_NAMES.custom);
        if (customItem) {
            customItem.domain = "[]";
        }
        // Deactivate every other period in the query silently, leave target untouched.
        for (const name of ALL_PERIOD_NAMES) {
            if (name === PERIOD_FILTER_NAMES[period]) {
                continue;
            }
            const item = findSearchItemByName(searchModel, name);
            if (item) {
                const idx = (searchModel.query || []).findIndex((entry) => entry.searchItemId === item.id);
                if (idx >= 0) {
                    searchModel.query.splice(idx, 1);
                }
            }
        }
        // Activate target if needed.
        if (!isItemActive(searchModel, targetItem)) {
            searchModel.query.push({ searchItemId: targetItem.id });
        }
        this._goldverseForceNotify(searchModel);
        this.goldverseToolbarState.period = period;
        this.goldverseToolbarState.customOpen = false;
    },

    goldverseApplyCustomRange() {
        if (!this.isGoldverseReportToolbar || !this.goldverseReportConfig) {
            return;
        }
        const fromValue = this.goldverseToolbarState.customFrom;
        const toValue = this.goldverseToolbarState.customTo;
        if (!fromValue || !toValue) {
            window.alert(_t("Please select both From and To dates."));
            return;
        }
        if (fromValue > toValue) {
            window.alert(_t("The From date must be earlier than or equal to the To date."));
            return;
        }
        const fromDateTime = DateTime.fromISO(fromValue);
        const toDateTime = DateTime.fromISO(toValue);
        if (!fromDateTime.isValid || !toDateTime.isValid) {
            window.alert(_t("Invalid date selection."));
            return;
        }

        const searchModel = this.env.searchModel;
        const customItem = findSearchItemByName(searchModel, PERIOD_FILTER_NAMES.custom);
        if (!customItem) {
            return;
        }

        const newDomain = buildDomainForRange(
            this.goldverseReportConfig.dateField,
            this.goldverseDateFieldType,
            fromDateTime,
            toDateTime
        );

        // Drop every other period filter silently from the query.
        for (const name of ALL_PERIOD_NAMES) {
            if (name === PERIOD_FILTER_NAMES.custom) {
                continue;
            }
            const item = findSearchItemByName(searchModel, name);
            if (item) {
                const idx = (searchModel.query || []).findIndex((entry) => entry.searchItemId === item.id);
                if (idx >= 0) {
                    searchModel.query.splice(idx, 1);
                }
            }
        }
        // Mutate the custom-range item's domain in place.
        customItem.domain = newDomain;
        // Ensure the custom item is part of the active query.
        if (!isItemActive(searchModel, customItem)) {
            searchModel.query.push({ searchItemId: customItem.id });
        }
        this._goldverseForceNotify(searchModel);
        this.goldverseToolbarState.period = "custom";
        this.goldverseToolbarState.customOpen = false;
    },

    goldverseClearCustomRange() {
        const searchModel = this.env.searchModel;
        if (!this.isGoldverseReportToolbar) {
            return;
        }
        const customItem = findSearchItemByName(searchModel, PERIOD_FILTER_NAMES.custom);
        if (customItem) {
            customItem.domain = "[]";
        }
        // Drop every period entry silently from the query, then activate Today.
        for (const name of ALL_PERIOD_NAMES) {
            const item = findSearchItemByName(searchModel, name);
            if (item) {
                const idx = (searchModel.query || []).findIndex((entry) => entry.searchItemId === item.id);
                if (idx >= 0) {
                    searchModel.query.splice(idx, 1);
                }
            }
        }
        const todayItem = findSearchItemByName(searchModel, PERIOD_FILTER_NAMES.today);
        if (todayItem) {
            searchModel.query.push({ searchItemId: todayItem.id });
        }
        this._goldverseForceNotify(searchModel);
        this.goldverseToolbarState.period = "today";
        this.goldverseToolbarState.customOpen = false;
        this.goldverseToolbarState.customFrom = DateTime.local().toISODate();
        this.goldverseToolbarState.customTo = DateTime.local().toISODate();
    },

    goldverseSelectCustomer(customerType) {
        if (!this.hasGoldverseCustomerFilters) {
            return;
        }
        const searchModel = this.env.searchModel;
        const targetItem = findSearchItemByName(searchModel, CUSTOMER_FILTER_NAMES[customerType]);
        if (!targetItem) {
            return;
        }
        for (const name of Object.values(CUSTOMER_FILTER_NAMES)) {
            if (name === CUSTOMER_FILTER_NAMES[customerType]) {
                continue;
            }
            const item = findSearchItemByName(searchModel, name);
            if (item) {
                const idx = (searchModel.query || []).findIndex((entry) => entry.searchItemId === item.id);
                if (idx >= 0) {
                    searchModel.query.splice(idx, 1);
                }
            }
        }
        if (!isItemActive(searchModel, targetItem)) {
            searchModel.query.push({ searchItemId: targetItem.id });
        }
        this._goldverseForceNotify(searchModel);
        this.goldverseToolbarState.customerType = customerType;
    },

    goldverseToggleCustomPanel() {
        this.goldverseToolbarState.customOpen = !this.goldverseToolbarState.customOpen;
    },

    goldverseRefreshToolbar() {
        if (typeof this.env.searchModel?.search === "function") {
            this.env.searchModel.search();
        }
    },

    _goldverseOnOutsideClick(ev) {
        if (!this.goldverseToolbarState.customOpen) {
            return;
        }
        const root = ev.target.closest(".goldverse-report-custom-pop");
        const trigger = ev.target.closest(".goldverse-report-custom-trigger");
        if (root || trigger) {
            return;
        }
        this.goldverseToolbarState.customOpen = false;
    },

    willUnmount() {
        if (this._goldverseBoundOutsideClick) {
            document.removeEventListener("mousedown", this._goldverseBoundOutsideClick, true);
        }
        if (typeof super.willUnmount === "function") {
            super.willUnmount(...arguments);
        }
    },
});
