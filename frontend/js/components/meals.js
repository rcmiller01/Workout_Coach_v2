/**
 * AI Fitness Coach v1 — Meals/Nutrition Component
 */
const MealsComponent = {
    async render(data) {
        const container = document.getElementById('meals-content');

        // Always show log meal button and logged meals
        let html = '';

        // Log Meal button - always visible
        html += `
            <div style="margin-bottom: 16px;">
                <button class="btn-primary" onclick="App.showMealModal()" style="width: 100%;">
                    + Log a Meal
                </button>
            </div>
        `;

        // Fetch today's logged meals (UTC date to match server storage)
        const today = new Date().toISOString().split('T')[0];
        let loggedMeals = [];
        try {
            const history = await api.getMealHistory(today);
            loggedMeals = history.entries || [];
        } catch (err) {
            console.error('Failed to fetch meal history:', err);
        }

        // Show logged meals totals if any
        if (loggedMeals.length > 0) {
            const loggedTotals = {
                calories: loggedMeals.reduce((sum, m) => sum + (m.calories || 0), 0),
                protein_g: loggedMeals.reduce((sum, m) => sum + (m.protein_g || 0), 0),
                carbs_g: loggedMeals.reduce((sum, m) => sum + (m.carbs_g || 0), 0),
                fat_g: loggedMeals.reduce((sum, m) => sum + (m.fat_g || 0), 0),
            };

            html += `
                <div class="card" style="margin-bottom: 16px; background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(99, 102, 241, 0.04) 100%); border-color: rgba(59, 130, 246, 0.15);">
                    <div class="card-header">
                        <span class="card-label">Today's Logged</span>
                        <span class="card-badge">${loggedMeals.length} meals</span>
                    </div>
                    <div class="meal-macros">
                        <div class="meal-macro"><strong>${loggedTotals.calories}</strong> kcal</div>
                        <div class="meal-macro"><strong>${loggedTotals.protein_g.toFixed(0)}</strong>g P</div>
                        <div class="meal-macro"><strong>${loggedTotals.carbs_g.toFixed(0)}</strong>g C</div>
                        <div class="meal-macro"><strong>${loggedTotals.fat_g.toFixed(0)}</strong>g F</div>
                    </div>
                </div>
            `;

            // List logged meals
            html += `<h3 style="margin: 16px 0 12px; font-size: 14px; color: var(--text-secondary);">Logged Meals</h3>`;
            loggedMeals.forEach(meal => {
                const typeLabel = this.formatMealType(meal.meal_type);
                html += `
                    <div class="meal-card" style="position: relative; opacity: 0.9; border-left: 3px solid var(--accent-blue);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div class="meal-type">${typeLabel}</div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 10px; color: var(--text-tertiary);">${new Date(meal.date).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                <button onclick="App.deleteMealLog('${meal.id}')" title="Remove" style="background: none; border: none; color: var(--accent-red, #ef4444); cursor: pointer; font-size: 14px; padding: 2px 4px; opacity: 0.6; transition: opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.6">✕</button>
                            </div>
                        </div>
                        <div class="meal-name" style="margin-top: 4px; font-weight: 600;">${meal.name}</div>
                        ${meal.notes ? `<div style="font-size: 11px; color: var(--accent-amber); margin: 4px 0; font-style: italic;">↳ ${meal.notes}</div>` : ''}
                        <div class="meal-macros" style="margin-top: 8px;">
                            ${meal.calories ? `<div class="meal-macro"><strong>${meal.calories}</strong> kcal</div>` : ''}
                            ${meal.protein_g ? `<div class="meal-macro"><strong>${meal.protein_g}</strong>g P</div>` : ''}
                            ${meal.carbs_g ? `<div class="meal-macro"><strong>${meal.carbs_g}</strong>g C</div>` : ''}
                            ${meal.fat_g ? `<div class="meal-macro"><strong>${meal.fat_g}</strong>g F</div>` : ''}
                        </div>
                    </div>`;
            });
        }

        if (!data || data.message === "No active plan") {
            html += `
                <div class="empty-state" style="margin-top: 24px; border: 1px dashed var(--border-card); border-radius: var(--radius-lg); background: rgba(255,255,255,0.01);">
                    <p style="margin-bottom: 12px;">No active nutrition plan found.</p>
                    <button class="btn-secondary" onclick="App.generatePlan()">
                        <svg style="width:16px; height:16px; margin-right:8px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></path></svg>
                        Generate Weekly Plan
                    </button>
                    <p style="font-size: 11px; margin-top: 12px; color: var(--text-tertiary);">You can still log meals manually above.</p>
                </div>`;
            container.innerHTML = html;
            return;
        }

        if (data.active_summary) {
            html += `
                <div style="background: rgba(79, 140, 255, 0.1); border: 1px solid rgba(79, 140, 255, 0.2); padding: 8px 12px; border-radius: 6px; margin-bottom: 16px; font-size: 13px; color: var(--accent-blue);">
                    <strong>ℹ️</strong> ${data.active_summary}
                </div>
            `;
        }

        // 1. Current Nutrition Targets
        const bt = data.baseline_targets;
        const ct = data.current_targets;
        const isAdjusted = ct.calories !== bt.calories || ct.protein_g !== bt.protein_g;

        html += `
            <div class="card" style="margin-bottom: 24px;">
                <h3 style="margin: 0 0 16px; font-size: 16px; color: var(--text-primary);">Daily Nutrition Targets</h3>
                
                <div style="display: flex; gap: 16px; flex-wrap: wrap;">
                    <div style="flex:1; min-width: 100px; text-align: center; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                        <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px;">Calories</div>
                        <div style="font-size: 20px; font-weight: 700; color: ${isAdjusted ? 'var(--accent-amber)' : 'var(--text-primary)'};">
                            ${ct.calories}
                        </div>
                    </div>
                    <div style="flex:1; min-width: 80px; text-align: center; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                        <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px;">Protein</div>
                        <div style="font-size: 20px; font-weight: 700;">${ct.protein_g}g</div>
                    </div>
                    <div style="flex:1; min-width: 80px; text-align: center; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                        <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px;">Carbs</div>
                        <div style="font-size: 20px; font-weight: 700;">${ct.carbs_g != null ? ct.carbs_g + 'g' : '—'}</div>
                    </div>
                    <div style="flex:1; min-width: 80px; text-align: center; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px;">
                        <div style="font-size: 12px; color: var(--text-tertiary); margin-bottom: 4px;">Fat</div>
                        <div style="font-size: 20px; font-weight: 700;">${ct.fat_g != null ? ct.fat_g + 'g' : '—'}</div>
                    </div>
                </div>
            </div>
        `;

        // 2. Nutrition Revision Tracking (Before vs After)
        if (data.nutrition_revisions && data.nutrition_revisions.length > 0) {
            html += `<h3 style="margin: 32px 0 16px; font-size: 16px; color: var(--text-secondary);">Nutrition Adjustments</h3>`;
            
            data.nutrition_revisions.forEach(rev => {
                const config = DashboardComponent._getStatusConfig(rev.status);
                const isTerminal = ['reverted', 'superseded', 'blocked'].includes(rev.status);
                const calAdjust = rev.patch?.meal_plan?.calorie_adjust || 0;
                
                // Calculate the Before vs After delta for this specific revision context.
                // In our model, base is always bt, and the delta is calAdjust.
                const beforeCal = bt.calories;
                const afterCal = bt.calories + calAdjust;
                const triggerLabel = (rev.trigger || '').replace(/_/g, ' ');

                html += `
                    <div class="card" style="margin-bottom:12px; padding:16px; ${isTerminal ? 'opacity:0.6;' : ''}">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <span style="font-size:12px; font-weight:600; text-transform:uppercase; color:var(--text-primary);">${triggerLabel}</span>
                            <span style="background:${config.bgColor}; color:${config.color}; font-size:11px; padding:2px 8px; border-radius:6px;">
                                ${config.icon} ${config.label}
                            </span>
                        </div>
                        
                        <div style="color:var(--text-secondary); font-size:13px; line-height:1.4; margin-bottom:16px;">
                            ${rev.reason}
                        </div>
                        
                        ${calAdjust !== 0 ? `
                        <div style="display:flex; align-items:center; gap:16px; background:rgba(0,0,0,0.2); padding:10px; border-radius:6px; font-family:monospace; font-size:13px;">
                            <div style="color:var(--text-tertiary);">
                                <div style="font-size:10px; margin-bottom:2px;">Original</div>
                                <div>${beforeCal} kcal</div>
                            </div>
                            <div style="color:var(--text-tertiary);">→</div>
                            <div style="color: ${calAdjust > 0 ? 'var(--accent-green)' : 'var(--accent-amber)'}; font-weight:bold;">
                                <div style="font-size:10px; margin-bottom:2px;">Adjusted</div>
                                <div>${afterCal} kcal</div>
                            </div>
                            <div style="margin-left:auto; color: ${calAdjust > 0 ? 'var(--accent-green)' : 'var(--accent-red)'};">
                                ${calAdjust > 0 ? '+' : ''}${calAdjust}
                            </div>
                        </div>
                        ` : ''}

                        ${rev.status_reason ? `<div style="font-size:12px; color:${config.color}; margin-top:12px; font-style:italic;">${rev.status_reason}</div>` : ''}
                    </div>
                `;
            });
        }

        // 3. Today's Meals
        html += `<h3 style="margin: 32px 0 16px; font-size: 16px; color: var(--text-secondary);">Today's Planned Meals</h3>`;
        
        if (!data.meals || data.meals.length === 0) {
            html += `<div class="empty-state">No meals planned for today.</div>`;
        } else {
            // Daily totals summary from meals
            if (data.totals) {
                html += `
                    <div class="card" style="margin-bottom: 16px; background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(52, 211, 153, 0.04) 100%); border-color: rgba(16, 185, 129, 0.15);">
                        <div class="card-header">
                            <span class="card-label">Planned Totals</span>
                        </div>
                        <div class="meal-macros">
                            <div class="meal-macro"><strong>${data.totals.calories || '--'}</strong> kcal</div>
                            <div class="meal-macro"><strong>${data.totals.protein_g || '--'}</strong>g protein</div>
                            <div class="meal-macro"><strong>${data.totals.carbs_g || '--'}</strong>g carbs</div>
                            <div class="meal-macro"><strong>${data.totals.fat_g || '--'}</strong>g fat</div>
                        </div>
                    </div>`;
            }

            // Build a set of logged planned meal names for visual distinction
            const loggedPlannedNames = new Set(
                loggedMeals
                    .filter(m => m.is_planned)
                    .map(m => m.name.toLowerCase().trim())
            );

            // Individual meals
            data.meals.forEach((meal, idx) => {
                const typeLabel = this.formatMealType(meal.meal_type);
                const servings = meal.servings ? `<span style="font-size: 11px; padding: 2px 6px; background: rgba(255,255,255,0.1); border-radius: 4px; margin-left: auto;">${meal.servings} servings</span>` : '';
                // Handle both flat macros (meal.calories) and nested macros (meal.macros.calories)
                const cal = meal.calories || (meal.macros && meal.macros.calories) || 0;
                const pro = meal.protein_g || (meal.macros && meal.macros.protein_g) || 0;
                const carb = meal.carbs_g || (meal.macros && meal.macros.carbs_g) || 0;
                const fat = meal.fat_g || (meal.macros && meal.macros.fat_g) || 0;

                const isLogged = loggedPlannedNames.has((meal.name || '').toLowerCase().trim());

                // Encode meal data for the log button
                const mealJson = encodeURIComponent(JSON.stringify({
                    meal_type: meal.meal_type, name: meal.name,
                    calories: cal, protein_g: pro, carbs_g: carb, fat_g: fat,
                    servings: meal.servings || 1, is_planned: true
                }));

                html += `
                    <div class="meal-card" style="position: relative; ${isLogged ? 'opacity: 0.5; border-left: 3px solid var(--accent-green, #10b981);' : ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div class="meal-type">${typeLabel}</div>
                            ${isLogged ? '<span style="font-size: 11px; padding: 2px 8px; background: rgba(16, 185, 129, 0.15); color: var(--accent-green, #10b981); border-radius: 4px; margin-left: auto;">✓ Logged</span>' : servings}
                        </div>
                        <div class="meal-name" style="margin-top: 4px; font-weight: 600;">${meal.name || 'Unnamed Meal'}</div>
                        ${meal.notes ? `<div style="font-size: 11px; color: var(--accent-amber); margin: 4px 0 8px; font-style: italic;">↳ ${meal.notes}</div>` : ''}

                        <div class="meal-macros" style="margin-top: 8px;">
                            ${cal ? `<div class="meal-macro"><strong>${cal}</strong> kcal</div>` : ''}
                            ${pro ? `<div class="meal-macro"><strong>${pro}</strong>g P</div>` : ''}
                            ${carb ? `<div class="meal-macro"><strong>${carb}</strong>g C</div>` : ''}
                            ${fat ? `<div class="meal-macro"><strong>${fat}</strong>g F</div>` : ''}
                        </div>
                        ${isLogged
                            ? `<div style="margin-top: 10px; width: 100%; padding: 8px; font-size: 12px; text-align: center; color: var(--accent-green, #10b981); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 6px;">✓ Already logged</div>`
                            : `<button onclick="App.logPlannedMeal('${mealJson}')" class="btn-secondary" style="margin-top: 10px; width: 100%; padding: 8px; font-size: 12px;">✓ Log as Eaten</button>`
                        }
                    </div>`;
            });
        }

        container.innerHTML = html;
    },

    formatMealType(type) {
        const labels = {
            breakfast: '🌅 Breakfast',
            lunch: '☀️ Lunch',
            dinner: '🌙 Dinner',
            snack_1: '🍎 Snack',
            snack_2: '🍎 Snack 2',
            snack_3: '🍎 Snack 3',
            snack: '🍎 Snack',
        };
        return labels[type] || type.charAt(0).toUpperCase() + type.slice(1);
    }
};
