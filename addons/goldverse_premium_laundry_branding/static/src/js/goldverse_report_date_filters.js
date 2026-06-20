/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useState } from "@odoo/owl";

const REPORT_ACTION_IDS = new Set([628, 645, 649, 651, 665, 684, 690, 691, 692, 693, 694, 731]);
const REPORT_FILTER_CONFIG = {
    "aimaze.laundry.order": {
        dateField: "order_date",
    },
    "aimaze.laundry.delivery": {
        dateField: "pickup_datetime",
    },
    "aimaze.laundry.inventory.usage": {
        dateField: "date",
    },
    "aimaze.laundry.staff.task": {
        dateField: "start_time",
    },
    "aimaze.laundry.branch.profitability": {
        dateField: "date_from",
    },
    "account.payment": {
        dateField: "date",
    },
    "account.move.line": {
        dateField: "date",
    },
    "aimaze.customer.wallet.transaction": {
        dateField: "date",
    },
};
const PERIOD_FILTER_NAMES = {
    today: "today",
    mtd: "gv_mtd",
    ytd: "gv_ytd",
    itd: "gv_itd",
};
const CUSTOMER_FILTER_NAMES = {
    all: "gv_all_customers",
    b2c: "gv_b2c",
    b2b: "gv_b2b",
};
const CUSTOM_FILTER_PREFIX = "__goldverse_report_custom_date__:";

function normalizeDateValue(value) {
    return typeof value === "string" ? value.slice(0, 10) : "";
}

function currentDateValue() {
    return new Date().toISOString().slice(0, 10);
}

function getSearchItemByName(searchModel, name) {
    return searchModel?.getSearchItems((item) => item.name === name)?.find((item) => item);
}

function getCustomFilterItems(searchModel) {
    return (
        searchModel?.getSearchItems((item) =>
            String(item.description || "").startsWith(CUSTOM_FILTER_PREFIX)
        ) || []
    );
}

function getActiveQueryEntries(searchModel, item) {
    return (searchModel?.query || []).filter((entry) => entry.searchItemId === item.id);
}

patch(SearchBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.goldverseSearchToolbarState = useState({
            period: "",
            customerType: "",
            customFrom: "",
            customTo: "",
        });
        useBus(this.env.searchModel, "update", () => this.goldverseSyncSearchToolbarState());
        this.goldverseSyncSearchToolbarState();
    },

    get goldverseSearchReportConfig() {
        return REPORT_FILTER_CONFIG[this.env.searchModel?.resModel] || null;
    },

    get isGoldverseSearchToolbar() {
        if (!this.goldverseSearchReportConfig || !this.env.searchModel) {
            return false;
        }
        const rawActionId =
            this.env?.config?.actionId ||
            this.env?.config?.currentEmbeddedActionId;
        const actionId = Number(rawActionId);
        const hasPeriodMarkers = ["today", "gv_mtd", "gv_ytd", "gv_itd", "gv_custom"].some(
            (name) => Boolean(getSearchItemByName(this.env.searchModel, name))
        );
        const hasCustomerMarkers = ["gv_all_customers", "gv_b2c", "gv_b2b"].some(
            (name) => Boolean(getSearchItemByName(this.env.searchModel, name))
        );
        return REPORT_ACTION_IDS.has(actionId) || hasPeriodMarkers || hasCustomerMarkers;
    },

    get goldverseSearchActivePeriod() {
        return this.goldverseSearchToolbarState.period || "today";
    },

    get hasGoldverseSearchPeriodFilters() {
        return Object.values(PERIOD_FILTER_NAMES).every((name) =>
            Boolean(getSearchItemByName(this.env.searchModel, name))
        );
    },

    get hasGoldverseSearchCustomerFilters() {
        return Object.values(CUSTOMER_FILTER_NAMES).every((name) =>
            Boolean(getSearchItemByName(this.env.searchModel, name))
        );
    },

    goldverseSearchButtonClass(period) {
        return `btn ${this.goldverseSearchActivePeriod === period ? "btn-primary" : "btn-secondary"}`;
    },

    goldverseSearchCustomerButtonClass(customerType) {
        const activeType = this.goldverseSearchToolbarState.customerType || "all";
        return `btn ${activeType === customerType ? "btn-primary" : "btn-secondary"}`;
    },

    goldverseSyncSearchToolbarState() {
        if (!this.isGoldverseSearchToolbar || !this.env.searchModel) {
            return;
        }

        let activePeriod = "today";
        for (const [period, searchName] of Object.entries(PERIOD_FILTER_NAMES)) {
            const item = getSearchItemByName(this.env.searchModel, searchName);
            if (item && getActiveQueryEntries(this.env.searchModel, item).length) {
                activePeriod = period;
                break;
            }
        }

        const customItem = activePeriod === "today" && getCustomFilterItems(this.env.searchModel).find(
            (item) => getActiveQueryEntries(this.env.searchModel, item).length
        );
        if (customItem) {
            activePeriod = "custom";
            const marker = String(customItem.description || "").replace(CUSTOM_FILTER_PREFIX, "");
            const [fromValue, toValue] = marker.split("|");
            this.goldverseSearchToolbarState.customFrom = normalizeDateValue(fromValue);
            this.goldverseSearchToolbarState.customTo = normalizeDateValue(toValue);
        }

        this.goldverseSearchToolbarState.period = activePeriod;

        for (const [customerType, searchName] of Object.entries(CUSTOMER_FILTER_NAMES)) {
            const item = getSearchItemByName(this.env.searchModel, searchName);
            if (item && getActiveQueryEntries(this.env.searchModel, item).length) {
                this.goldverseSearchToolbarState.customerType = customerType;
                return;
            }
        }

        this.goldverseSearchToolbarState.customerType = "all";
    },

    goldverseClearSearchDateFilters() {
        if (!this.env.searchModel) {
            return;
        }

        for (const searchName of Object.values(PERIOD_FILTER_NAMES)) {
            const item = getSearchItemByName(this.env.searchModel, searchName);
            if (item && getActiveQueryEntries(this.env.searchModel, item).length) {
                this.env.searchModel.toggleSearchItem(item.id);
            }
        }

        const customDateItem = getSearchItemByName(this.env.searchModel, "gv_custom");
        if (customDateItem) {
            for (const entry of getActiveQueryEntries(this.env.searchModel, customDateItem)) {
                this.env.searchModel.toggleDateFilter(customDateItem.id, entry.generatorId);
            }
        }

        for (const item of getCustomFilterItems(this.env.searchModel)) {
            if (getActiveQueryEntries(this.env.searchModel, item).length) {
                this.env.searchModel.deactivateGroup(item.groupId);
            }
        }
    },

    goldverseApplySearchPeriod(period) {
        if (!this.isGoldverseSearchToolbar || !this.env.searchModel) {
            return;
        }

        if (period === "custom") {
            this.goldverseSearchToolbarState.period = "custom";
            if (!this.goldverseSearchToolbarState.customFrom) {
                this.goldverseSearchToolbarState.customFrom = currentDateValue();
            }
            if (!this.goldverseSearchToolbarState.customTo) {
                this.goldverseSearchToolbarState.customTo = this.goldverseSearchToolbarState.customFrom;
            }
            return;
        }

        this.goldverseClearSearchDateFilters();
        const item = getSearchItemByName(this.env.searchModel, PERIOD_FILTER_NAMES[period]);
        if (item) {
            this.env.searchModel.toggleSearchItem(item.id);
        }
        this.goldverseSearchToolbarState.period = period;
    },

    goldverseClearSearchCustomerFilters() {
        if (!this.env.searchModel) {
            return;
        }

        for (const searchName of Object.values(CUSTOMER_FILTER_NAMES)) {
            const item = getSearchItemByName(this.env.searchModel, searchName);
            if (item && getActiveQueryEntries(this.env.searchModel, item).length) {
                this.env.searchModel.toggleSearchItem(item.id);
            }
        }
    },

    goldverseApplySearchCustomerType(customerType) {
        if (!this.isGoldverseSearchToolbar || !this.env.searchModel || !this.hasGoldverseSearchCustomerFilters) {
            return;
        }

        this.goldverseClearSearchCustomerFilters();
        const item = getSearchItemByName(this.env.searchModel, CUSTOMER_FILTER_NAMES[customerType]);
        if (item) {
            this.env.searchModel.toggleSearchItem(item.id);
        }
        this.goldverseSearchToolbarState.customerType = customerType;
    },

    goldverseApplySearchCustomRange() {
        if (!this.isGoldverseSearchToolbar || !this.env.searchModel || !this.goldverseSearchReportConfig) {
            return;
        }

        const fromValue = normalizeDateValue(this.goldverseSearchToolbarState.customFrom);
        const toValue = normalizeDateValue(this.goldverseSearchToolbarState.customTo);
        if (!fromValue || !toValue) {
            window.alert(_t("Please select both From and To dates."));
            return;
        }
        if (fromValue > toValue) {
            window.alert(_t("The From date must be earlier than or equal to the To date."));
            return;
        }

        this.goldverseClearSearchDateFilters();
        this.env.searchModel.createNewFilters([
            {
                description: `${CUSTOM_FILTER_PREFIX}${fromValue}|${toValue}`,
                domain: [
                    [this.goldverseSearchReportConfig.dateField, ">=", `${fromValue} 00:00:00`],
                    [this.goldverseSearchReportConfig.dateField, "<=", `${toValue} 23:59:59`],
                ],
                invisible: "True",
            },
        ]);
        this.goldverseSearchToolbarState.period = "custom";
    },

    goldverseRefreshSearchToolbar() {
        window.location.reload();
    },
});
