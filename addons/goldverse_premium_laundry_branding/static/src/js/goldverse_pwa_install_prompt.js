import { MessagingMenu } from "@mail/core/public_web/messaging_menu";
import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

const WAQAR_INSTALL_PROMPT_RESET_KEY = "goldverse.waqarPwaInstallPromptReset";

function isWaqarSheikh() {
    const values = [user.name, user.login]
        .filter(Boolean)
        .map((value) => value.toLowerCase());
    return values.some(
        (value) =>
            value === "waqar sheikh" ||
            value.includes("waqar sheikh") ||
            value.includes("waqqarsheikh")
    );
}

function resetPwaDismissalForWaqar() {
    if (!isWaqarSheikh() || browser.sessionStorage.getItem(WAQAR_INSTALL_PROMPT_RESET_KEY)) {
        return;
    }
    const installationState = JSON.parse(
        browser.localStorage.getItem("pwaService.installationState") || "{}"
    );
    delete installationState["/odoo"];
    browser.localStorage.setItem(
        "pwaService.installationState",
        JSON.stringify(installationState)
    );
    browser.sessionStorage.setItem(WAQAR_INSTALL_PROMPT_RESET_KEY, "1");
}

resetPwaDismissalForWaqar();

patch(MessagingMenu.prototype, {
    get canPromptToInstall() {
        if (isWaqarSheikh() && this.pwa.isAvailable) {
            return true;
        }
        return super.canPromptToInstall;
    },
});
