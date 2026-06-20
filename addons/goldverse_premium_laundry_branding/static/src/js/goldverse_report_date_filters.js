/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { GraphController } from "@web/views/graph/graph_controller";
import { ListController } from "@web/views/list/list_controller";
import { PivotController } from "@web/views/pivot/pivot_controller";
import { useState } from "@odoo/owl";

const REPORT_FILTER_CLASS = "goldverse-report-date-list";
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

function applyGoldverseReportControllerPatch(ControllerClass, patchVersion) {
    if (ControllerClass.prototype.__goldverseReportDateFilterPatchVersion) {
        return;
    }
    patch(ControllerClass.prototype, {
        __goldverseReportDateFilterPatchVersion: patchVersion,

        setup() {
            super.setup(...arguments);
            this.goldverseReportFilterState = useState({
                toolbarEnabled: false,
                period: "",
                customerType: "",
                customFrom: "",
                customTo: "",
            });
            useBus(this.env.searchModel, "update", () => this.goldverseSyncReportFilterState());
            this.goldverseSyncReportFilterState();
        },

        get isGoldverseReportFilterView() {
            return Boolean(
                REPORT_FILTER_CONFIG[this.props.resModel] &&
                this.goldverseReportFilterState.toolbarEnabled
            );
        },

        goldverseComputeToolbarEnabled() {
            const className =
                this.archInfo?.className ||
                this.props.archInfo?.className ||
                this.props.className ||
                "";
            const rawActionId =
                this.env?.config?.actionId ||
                this.env?.config?.currentEmbeddedActionId ||
                this.props.info?.actionId ||
                this.props.actionId;
            const actionId = Number(rawActionId);
            const hasGoldverseSearchItems = [
                ...Object.values(PERIOD_FILTER_NAMES),
                ...Object.values(CUSTOMER_FILTER_NAMES),
                "gv_custom",
            ].some((name) => Boolean(this.goldverseGetSearchItemByName(name)));
            return Boolean(
                REPORT_FILTER_CONFIG[this.props.resModel] &&
                (
                    this.props.context?.goldverse_report_toolbar ||
                    className.includes(REPORT_FILTER_CLASS) ||
                    REPORT_ACTION_IDS.has(actionId) ||
                    hasGoldverseSearchItems
                )
            );
        },

        get isGoldverseReportFilterList() {
            return this.isGoldverseReportFilterView;
        },

        get goldverseReportConfig() {
            return REPORT_FILTER_CONFIG[this.props.resModel] || null;
        },

        get goldverseReportActivePeriod() {
            return this.goldverseReportFilterState.period || "today";
        },

        get hasGoldversePeriodFilters() {
            return Object.values(PERIOD_FILTER_NAMES).every((name) => Boolean(this.goldverseGetSearchItemByName(name)));
        },

        get hasGoldverseCustomerFilters() {
            return Object.values(CUSTOMER_FILTER_NAMES).every((name) => Boolean(this.goldverseGetSearchItemByName(name)));
        },

        goldverseReportButtonClass(period) {
            return `btn ${this.goldverseReportActivePeriod === period ? "btn-primary" : "btn-secondary"}`;
        },

        goldverseCustomerButtonClass(customerType) {
            const activeType = this.goldverseReportFilterState.customerType || "all";
            return `btn ${activeType === customerType ? "btn-primary" : "btn-secondary"}`;
        },

        goldverseGetSearchItemByName(name) {
            return this.env.searchModel
                ?.getSearchItems((item) => item.name === name)
                ?.find((item) => item);
        },

        goldverseGetCustomFilterItems() {
            return (
                this.env.searchModel?.getSearchItems((item) =>
                    String(item.description || "").startsWith(CUSTOM_FILTER_PREFIX)
                ) || []
            );
        },

        goldverseGetActiveQueryEntries(item) {
            return (this.env.searchModel?.query || []).filter(
                (entry) => entry.searchItemId === item.id
            );
        },

        goldverseSyncReportFilterState() {
            this.goldverseReportFilterState.toolbarEnabled = this.goldverseComputeToolbarEnabled();

            if (!this.goldverseReportFilterState.toolbarEnabled || !this.env.searchModel) {
                return;
            }

            let activePeriod = "today";
            for (const [period, searchName] of Object.entries(PERIOD_FILTER_NAMES)) {
                const item = this.goldverseGetSearchItemByName(searchName);
                if (item && this.goldverseGetActiveQueryEntries(item).length) {
                    activePeriod = period;
                    break;
                }
            }

            const customItem = activePeriod === "today" && this.goldverseGetCustomFilterItems().find(
                (item) => this.goldverseGetActiveQueryEntries(item).length
            );
            if (customItem) {
                activePeriod = "custom";
                const marker = String(customItem.description || "").replace(CUSTOM_FILTER_PREFIX, "");
                const [fromValue, toValue] = marker.split("|");
                this.goldverseReportFilterState.customFrom = normalizeDateValue(fromValue);
                this.goldverseReportFilterState.customTo = normalizeDateValue(toValue);
            }

            this.goldverseReportFilterState.period = activePeriod;

            for (const [customerType, searchName] of Object.entries(CUSTOMER_FILTER_NAMES)) {
                const item = this.goldverseGetSearchItemByName(searchName);
                if (item && this.goldverseGetActiveQueryEntries(item).length) {
                    this.goldverseReportFilterState.customerType = customerType;
                    return;
                }
            }

            this.goldverseReportFilterState.customerType = "all";
        },

        goldverseClearReportDateFilters() {
            if (!this.env.searchModel) {
                return;
            }

            for (const searchName of Object.values(PERIOD_FILTER_NAMES)) {
                const item = this.goldverseGetSearchItemByName(searchName);
                if (item && this.goldverseGetActiveQueryEntries(item).length) {
                    this.env.searchModel.toggleSearchItem(item.id);
                }
            }

            const customDateItem = this.goldverseGetSearchItemByName("gv_custom");
            if (customDateItem) {
                for (const entry of this.goldverseGetActiveQueryEntries(customDateItem)) {
                    this.env.searchModel.toggleDateFilter(customDateItem.id, entry.generatorId);
                }
            }

            for (const item of this.goldverseGetCustomFilterItems()) {
                if (this.goldverseGetActiveQueryEntries(item).length) {
                    this.env.searchModel.deactivateGroup(item.groupId);
                }
            }
        },

        goldverseApplyReportPeriod(period) {
            if (!this.isGoldverseReportFilterView || !this.env.searchModel) {
                return;
            }

            if (period === "custom") {
                this.goldverseReportFilterState.period = "custom";
                if (!this.goldverseReportFilterState.customFrom) {
                    this.goldverseReportFilterState.customFrom = currentDateValue();
                }
                if (!this.goldverseReportFilterState.customTo) {
                    this.goldverseReportFilterState.customTo = this.goldverseReportFilterState.customFrom;
                }
                return;
            }

            this.goldverseClearReportDateFilters();
            const item = this.goldverseGetSearchItemByName(PERIOD_FILTER_NAMES[period]);
            if (item) {
                this.env.searchModel.toggleSearchItem(item.id);
            }
            this.goldverseReportFilterState.period = period;
        },

        goldverseClearCustomerFilters() {
            if (!this.env.searchModel) {
                return;
            }

            for (const searchName of Object.values(CUSTOMER_FILTER_NAMES)) {
                const item = this.goldverseGetSearchItemByName(searchName);
                if (item && this.goldverseGetActiveQueryEntries(item).length) {
                    this.env.searchModel.toggleSearchItem(item.id);
                }
            }
        },

        goldverseApplyCustomerType(customerType) {
            if (!this.isGoldverseReportFilterView || !this.env.searchModel || !this.hasGoldverseCustomerFilters) {
                return;
            }

            this.goldverseClearCustomerFilters();
            const item = this.goldverseGetSearchItemByName(CUSTOMER_FILTER_NAMES[customerType]);
            if (item) {
                this.env.searchModel.toggleSearchItem(item.id);
            }
            this.goldverseReportFilterState.customerType = customerType;
        },

        goldverseApplyCustomReportRange() {
            if (!this.isGoldverseReportFilterView || !this.env.searchModel) {
                return;
            }

            const fromValue = normalizeDateValue(this.goldverseReportFilterState.customFrom);
            const toValue = normalizeDateValue(this.goldverseReportFilterState.customTo);
            if (!fromValue || !toValue) {
                window.alert(_t("Please select both From and To dates."));
                return;
            }
            if (fromValue > toValue) {
                window.alert(_t("The From date must be earlier than or equal to the To date."));
                return;
            }

            this.goldverseClearReportDateFilters();
            this.env.searchModel.createNewFilters([
                {
                    description: `${CUSTOM_FILTER_PREFIX}${fromValue}|${toValue}`,
                    domain: [
                        [this.goldverseReportConfig.dateField, ">=", `${fromValue} 00:00:00`],
                        [this.goldverseReportConfig.dateField, "<=", `${toValue} 23:59:59`],
                    ],
                    invisible: "True",
                },
            ]);
            this.goldverseReportFilterState.period = "custom";
        },

        async goldverseRefreshReportList() {
            if (!this.isGoldverseReportFilterView || !this.model?.load) {
                return;
            }
            await this.model.load();
        },
    });
}

applyGoldverseReportControllerPatch(ListController, 2);
applyGoldverseReportControllerPatch(PivotController, 2);
applyGoldverseReportControllerPatch(GraphController, 2);
