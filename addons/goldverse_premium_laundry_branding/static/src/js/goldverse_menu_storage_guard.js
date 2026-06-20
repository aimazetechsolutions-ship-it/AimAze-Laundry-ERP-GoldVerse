/** @odoo-module **/

import { browser } from "@web/core/browser/browser";

const GUARDED_KEYS = new Set(["webclient_menus", "webclient_menus_version"]);

function isQuotaExceeded(error) {
    return Boolean(
        error &&
        (
            error.name === "QuotaExceededError" ||
            error.code === 22 ||
            String(error.message || "").toLowerCase().includes("quota")
        )
    );
}

const originalSetItem = browser.localStorage?.setItem?.bind(browser.localStorage);

if (originalSetItem && !browser.localStorage.__goldverseMenuStorageGuardApplied) {
    browser.localStorage.setItem = function (key, value) {
        try {
            return originalSetItem(key, value);
        } catch (error) {
            if (!GUARDED_KEYS.has(key) || !isQuotaExceeded(error)) {
                throw error;
            }
            try {
                browser.localStorage.removeItem("webclient_menus");
                browser.localStorage.removeItem("webclient_menus_version");
                return originalSetItem(key, value);
            } catch (retryError) {
                if (!isQuotaExceeded(retryError)) {
                    throw retryError;
                }
                // Skip menu caching quietly when the browser storage is full.
                return undefined;
            }
        }
    };
    browser.localStorage.__goldverseMenuStorageGuardApplied = true;
}
