/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListRenderer } from "@web/views/list/list_renderer";

const ORDER_KEY_PREFIX = "goldverse_laundry_order_list_column_order";

function isGoldverseLaundryList(renderer) {
    return (
        renderer.props?.list?.resModel === "aimaze.laundry.order" &&
        renderer.props?.archInfo?.className?.includes("goldverse-laundry-order-list")
    );
}

function columnStorageKey(renderer) {
    const db = session.db || "db";
    const uid = session.uid || "uid";
    const model = renderer?.props?.list?.resModel || "aimaze.laundry.order";
    return `${ORDER_KEY_PREFIX}:${db}:${uid}:${model}`;
}

function readLegacyColumnOrder() {
    try {
        const value = JSON.parse(localStorage.getItem(ORDER_KEY_PREFIX) || "[]");
        return Array.isArray(value) ? value.filter(Boolean) : [];
    } catch {
        return [];
    }
}

function readColumnOrder(renderer) {
    try {
        const value = JSON.parse(localStorage.getItem(columnStorageKey(renderer)) || "[]");
        if (Array.isArray(value) && value.filter(Boolean).length) {
            return value.filter(Boolean);
        }
    } catch {
        // Ignore stale or hand-edited browser storage and fall back safely.
    }
    return readLegacyColumnOrder();
}

function writeColumnOrder(renderer, order) {
    localStorage.setItem(columnStorageKey(renderer), JSON.stringify(order.filter(Boolean)));
}

function applySavedOrder(renderer, columns) {
    const order = readColumnOrder(renderer);
    if (!order.length) {
        return columns;
    }
    const byName = new Map();
    const movable = [];
    const fixed = [];
    for (const column of columns) {
        if (column.type === "field" && column.name) {
            byName.set(column.name, column);
            movable.push(column);
        } else {
            fixed.push({ column, index: columns.indexOf(column) });
        }
    }
    const sorted = [
        ...order.map((name) => byName.get(name)).filter(Boolean),
        ...movable.filter((column) => !order.includes(column.name)),
    ];
    for (const item of fixed) {
        sorted.splice(Math.min(item.index, sorted.length), 0, item.column);
    }
    return sorted;
}

function moveNameBefore(order, source, target) {
    const clean = order.filter((name) => name && name !== source);
    const index = clean.indexOf(target);
    clean.splice(index >= 0 ? index : clean.length, 0, source);
    return clean;
}

function orderNamesFromHeader(row) {
    return Array.from(row.querySelectorAll("th[data-name]")).map((th) => th.dataset.name);
}

function reorderNamedCells(row, order, selector) {
    const namedCells = Array.from(row.querySelectorAll(selector));
    if (!namedCells.length) {
        return;
    }
    const byName = new Map(namedCells.map((cell) => [cell.dataset.name || cell.getAttribute("name"), cell]));
    const anchor = namedCells[namedCells.length - 1].nextSibling;
    for (const name of order) {
        const cell = byName.get(name);
        if (cell) {
            row.insertBefore(cell, anchor);
        }
    }
}

function applyOrderToTable(table, order) {
    const headerRow = table.querySelector("thead tr");
    if (headerRow) {
        reorderNamedCells(headerRow, order, "th[data-name]");
    }
    for (const row of table.querySelectorAll("tbody tr, tfoot tr")) {
        reorderNamedCells(row, order, "td[name]");
    }
}

function tableForHeader(header) {
    return header.closest(".goldverse-laundry-order-list table.o_list_table");
}

function rendererForTable(table) {
    return table.closest(".o_list_renderer")?.__owl__?.component || null;
}

if (!window.__goldverseLaundryColumnDragEnabled) {
    window.__goldverseLaundryColumnDragEnabled = true;

    document.addEventListener("dragstart", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        if (!header || ev.target.closest(".o_resize")) {
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", header.dataset.name);
        header.classList.add("goldverse-column-dragging");
    });

    document.addEventListener("dragend", (ev) => {
        ev.target.closest("th")?.classList.remove("goldverse-column-dragging");
        document
            .querySelectorAll(".goldverse-column-drop-target")
            .forEach((node) => node.classList.remove("goldverse-column-drop-target"));
    });

    document.addEventListener("dragover", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        if (!header) {
            return;
        }
        ev.preventDefault();
        header.classList.add("goldverse-column-drop-target");
    });

    document.addEventListener("dragleave", (ev) => {
        ev.target
            .closest(".goldverse-laundry-order-list table.o_list_table th[data-name]")
            ?.classList.remove("goldverse-column-drop-target");
    });

    document.addEventListener("drop", (ev) => {
        const header = ev.target.closest(".goldverse-laundry-order-list table.o_list_table th[data-name]");
        const table = header && tableForHeader(header);
        const source = ev.dataTransfer.getData("text/plain");
        const target = header?.dataset.name;
        if (!table || !source || !target || source === target) {
            return;
        }
        ev.preventDefault();
        const nextOrder = moveNameBefore(orderNamesFromHeader(table.querySelector("thead tr")), source, target);
        writeColumnOrder(rendererForTable(table), nextOrder);
        applyOrderToTable(table, nextOrder);
        header.classList.remove("goldverse-column-drop-target");
    });

    const markHeadersDraggable = () => {
        document
            .querySelectorAll(".goldverse-laundry-order-list table.o_list_table th[data-name]")
            .forEach((header) => {
                header.draggable = true;
                header.title = header.title || "Drag to move column. Use the edge handle to resize.";
            });
    };

    const observer = new MutationObserver(markHeadersDraggable);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    markHeadersDraggable();
}

if (ListRenderer.prototype.__goldverseLaundryListColumnPatchVersion !== 2) {
    patch(ListRenderer.prototype, {
        __goldverseLaundryListColumnPatchVersion: 2,

        getActiveColumns() {
            const columns = super.getActiveColumns(...arguments);
            return isGoldverseLaundryList(this) ? applySavedOrder(this, columns) : columns;
        },
    });
}
