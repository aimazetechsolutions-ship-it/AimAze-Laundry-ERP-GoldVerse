/** @odoo-module **/

import { browser } from "@web/core/browser/browser";

const GUARDED_KEYS = new Set(["webclient_menus", "webclient_menus_version"]);
const STORAGE_GUARD_FLAG = "__goldverseMenuStorageGuardApplied";

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

function guardMenuStorage(storage, originalSetItem) {
    if (!storage || !originalSetItem || storage[STORAGE_GUARD_FLAG]) {
        return;
    }

    const guardedSetItem = function (key, value) {
        try {
            return originalSetItem.call(this, key, value);
        } catch (error) {
            if (!GUARDED_KEYS.has(key) || !isQuotaExceeded(error)) {
                throw error;
            }
            try {
                this.removeItem("webclient_menus");
                this.removeItem("webclient_menus_version");
                return originalSetItem.call(this, key, value);
            } catch (retryError) {
                if (!isQuotaExceeded(retryError)) {
                    throw retryError;
                }
                // Skip menu caching quietly when the browser storage is full.
                return undefined;
            }
        }
    };

    try {
        Object.defineProperty(storage, "setItem", {
            value: guardedSetItem,
            configurable: true,
            writable: true,
        });
    } catch {
        storage.setItem = guardedSetItem;
    }
    storage[STORAGE_GUARD_FLAG] = true;
}

const storagePrototype = globalThis.Storage?.prototype;
if (storagePrototype?.setItem && !storagePrototype[STORAGE_GUARD_FLAG]) {
    const originalPrototypeSetItem = storagePrototype.setItem;
    guardMenuStorage(storagePrototype, originalPrototypeSetItem);
}

const originalStorageSetItem = browser.localStorage?.setItem;
if (originalStorageSetItem) {
    guardMenuStorage(browser.localStorage, originalStorageSetItem);
}
