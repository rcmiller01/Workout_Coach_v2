/**
 * AI Fitness Coach v1 — Client-side Router
 */
const Router = {
    currentRoute: 'dashboard',

    init() {
        // Bind nav buttons
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', () => {
                const route = btn.dataset.route;
                this.navigate(route);
            });
        });

        // Handle browser back/forward
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.route) {
                this.show(e.state.route);
            }
        });

        // Initial route from hash or default
        const hash = window.location.hash.replace('#', '');
        const initialRoute = hash || 'dashboard';
        this.navigate(initialRoute, false);
    },

    navigate(route, pushState = true) {
        this.show(route);
        if (pushState) {
            history.pushState({ route }, '', `#${route}`);
        }

        // Trigger data load for the new view
        if (typeof App !== 'undefined' && App.loadViewData) {
            App.loadViewData(route);
        }
    },

    show(route) {
        this.currentRoute = route;

        // Update nav
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.route === route);
        });

        // Update views
        document.querySelectorAll('.view').forEach(view => {
            view.classList.toggle('active', view.id === `view-${route}`);
        });
    }
};
