import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { debounce } from "@web/core/utils/timing";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";

const STORAGE_KEY = "distribuidora_chatter_open";
const BODY_CLASS = "o-distribuidora-chatter-open";

// The chatter (mail's <chatter/> block) is compiled into every form view by
// mail/static/src/chatter/web/form_compiler.js as ".o-mail-Form-chatter" -
// hiding/showing it is a single body-level CSS class (see chatter_toggle.scss),
// this component only owns the bubble that flips that class and remembers it.
export class DistribuidoraChatterToggle extends Component {
    static template = "distribuidora_chatter_toggle.ChatterToggle";
    static props = {};

    setup() {
        this.state = useState({
            isOpen: browser.localStorage.getItem(STORAGE_KEY) === "1",
            hasChatter: false,
        });
        this.applyBodyClass();

        this.checkChatter = this.checkChatter.bind(this);
        this.debouncedCheckChatter = debounce(this.checkChatter, 150);
        this.checkChatter();

        onMounted(() => {
            const root = document.querySelector(".o_action_manager") || document.body;
            this.observer = new MutationObserver(this.debouncedCheckChatter);
            this.observer.observe(root, { childList: true, subtree: true });
        });
        onWillUnmount(() => {
            this.observer?.disconnect();
            this.debouncedCheckChatter.cancel();
        });
    }

    checkChatter() {
        const hasChatter = !!document.querySelector(".o-mail-Form-chatter");
        if (hasChatter !== this.state.hasChatter) {
            this.state.hasChatter = hasChatter;
        }
    }

    applyBodyClass() {
        document.body.classList.toggle(BODY_CLASS, this.state.isOpen);
    }

    onClickToggle() {
        this.state.isOpen = !this.state.isOpen;
        this.applyBodyClass();
        browser.localStorage.setItem(STORAGE_KEY, this.state.isOpen ? "1" : "0");
    }
}

registry.category("main_components").add("distribuidora_chatter_toggle.ChatterToggle", {
    Component: DistribuidoraChatterToggle,
});
