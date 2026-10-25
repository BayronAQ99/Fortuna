import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillUnmount, useState } from "@odoo/owl";

// The sidebar only switches between apps (Clientes, Preventas, Facturación...).
// Each app's own sections/subsections stay in Odoo's native horizontal
// SectionsMenu (below the breadcrumb) instead of being duplicated here —
// that component already handles arbitrarily deep, wide menus (nested
// dropdowns, overflow into a "More" entry) without us reinventing it.
export class DistribuidoraSidebar extends Component {
    static template = "distribuidora_sidebar.Sidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.state = useState({ currentAppId: this.currentAppId });

        const onAppChanged = () => {
            this.state.currentAppId = this.currentAppId;
        };
        this.env.bus.addEventListener("MENUS:APP-CHANGED", onAppChanged);
        onWillUnmount(() => this.env.bus.removeEventListener("MENUS:APP-CHANGED", onAppChanged));
    }

    get apps() {
        return this.menuService.getApps();
    }

    get currentAppId() {
        const app = this.menuService.getCurrentApp();
        return app ? app.id : false;
    }

    onClickApp(app, ev) {
        ev.preventDefault();
        this.menuService.selectMenu(app);
    }
}

registry.category("main_components").add("distribuidora_sidebar.Sidebar", {
    Component: DistribuidoraSidebar,
});
