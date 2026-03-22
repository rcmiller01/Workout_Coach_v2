/**
 * AI Fitness Coach v1 — Shopping List Component
 */
const ShoppingComponent = {
    async render(data) {
        const container = document.getElementById('shopping-content');

        if (!data || data.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>No shopping list yet.</p>
                    <p style="color: var(--text-tertiary); font-size: 13px;">
                        Generate a meal plan to create your shopping list.
                    </p>
                </div>`;
            return;
        }

        // Group by category
        const categories = {};
        data.forEach(item => {
            const cat = item.category || 'Other';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(item);
        });

        // Sort categories
        const categoryOrder = ['Protein', 'Produce', 'Dairy', 'Grains', 'Pantry', 'Frozen', 'Other'];
        const sortedCategories = Object.entries(categories).sort(
            ([a], [b]) => (categoryOrder.indexOf(a) - categoryOrder.indexOf(b))
        );

        let html = '';
        sortedCategories.forEach(([category, items]) => {
            html += `
                <div class="shopping-category">
                    <div class="shopping-category-title">${category}</div>`;

            items.forEach((item, idx) => {
                html += `
                    <div class="shopping-item ${item.checked ? 'checked' : ''}"
                         data-name="${item.name}" onclick="ShoppingComponent.toggleItem(this)">
                        <div class="shopping-checkbox">
                            ${item.checked ? '<svg viewBox="0 0 24 24" fill="white" width="14" height="14"><polyline points="20,6 9,17 4,12" stroke="white" stroke-width="3" fill="none"></polyline></svg>' : ''}
                        </div>
                        <span class="shopping-item-name">${item.name}</span>
                        <span class="shopping-item-qty">${item.quantity}</span>
                    </div>`;
            });

            html += '</div>';
        });

        container.innerHTML = html;
    },

    toggleItem(el) {
        el.classList.toggle('checked');
        const checkbox = el.querySelector('.shopping-checkbox');
        if (el.classList.contains('checked')) {
            checkbox.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14"><polyline points="20,6 9,17 4,12" stroke="white" stroke-width="3" fill="none"></polyline></svg>';
        } else {
            checkbox.innerHTML = '';
        }
    }
};
