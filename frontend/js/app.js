/**
 * AI Fitness Coach v1 — Main Application
 */
const App = {
    userId: null,
    dashboardData: null,

    // Unit conversion helpers
    lbsToKg(lbs) { return lbs * 0.453592; },
    kgToLbs(kg) { return kg * 2.20462; },

    async init() {
        // Check for stored user ID
        this.userId = localStorage.getItem('coach_user_id');

        // Init router
        Router.init();

        if (!this.userId) {
            this.showSetup();
        } else {
            this.loadViewData('dashboard');
        }

        // Bind setup form
        const form = document.getElementById('setup-form');
        if (form) {
            form.addEventListener('submit', (e) => this.handleSetup(e));
        }

        // Bind generate plan button
        const btnGenerate = document.getElementById('btn-start-workout');
        if (btnGenerate) {
            btnGenerate.addEventListener('click', () => {
                if (this.dashboardData && this.dashboardData.workout) {
                    Router.navigate('workout');
                } else {
                    this.generatePlan();
                }
            });
        }

        // Bind weight form
        const weightForm = document.getElementById('weight-form');
        if (weightForm) {
            weightForm.addEventListener('submit', (e) => this.handleWeightLog(e));
        }

        // Bind meal form
        const mealForm = document.getElementById('meal-form');
        if (mealForm) {
            mealForm.addEventListener('submit', (e) => this.handleMealLog(e));
        }

        // Register service worker
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('sw.js').catch(() => {});
        }

        // Set greeting based on time
        this.updateGreeting();
    },

    updateGreeting() {
        const hour = new Date().getHours();
        const el = document.getElementById('greeting-text');
        if (!el) return;
        if (hour < 12) el.textContent = 'Good morning 💪';
        else if (hour < 17) el.textContent = 'Good afternoon 🔥';
        else el.textContent = 'Good evening 🌙';
    },

    showSetup() {
        const modal = document.getElementById('setup-modal');
        if (modal) modal.style.display = 'flex';
    },

    async handleSetup(e) {
        e.preventDefault();
        const form = e.target;
        const userId = crypto.randomUUID ? crypto.randomUUID() : 'user-' + Date.now();

        try {
            await api.createProfile({
                user_id: userId,
                goal: form.goal.value,
                days_per_week: parseInt(form.days_per_week.value),
                target_calories: parseInt(form.target_calories.value),
                target_protein_g: parseInt(form.target_protein_g.value),
            });

            this.userId = userId;
            localStorage.setItem('coach_user_id', userId);
            document.getElementById('setup-modal').style.display = 'none';
            this.loadViewData('dashboard');
        } catch (err) {
            alert('Setup failed: ' + err.message);
        }
    },

    async getActiveSummary(userId) {
        try {
            const revs = await api.getUserRevisions(userId);
            const active = revs.filter(r => ['pending', 'applied', 'approved'].includes(r.status));
            if (active.length === 0) return null;

            let strings = [];
            active.forEach(r => {
                const cal = r.patch?.meal_plan?.calorie_adjust;
                if (cal !== undefined) {
                    strings.push(`calories ${cal > 0 ? '+' : ''}${cal}`);
                }
                const vol = r.patch?.workout_plan?.global_modifier;
                if (vol !== undefined) {
                    const pct = Math.round(vol * 100);
                    strings.push(`volume ${pct > 0 ? '+' : ''}${pct}%`);
                }
            });
            
            // Deduplicate since we iterate multiple revisions, but we resolved to one effective state per area
            const uniqueStrings = [...new Set(strings)];
            
            if (uniqueStrings.length === 0) return null;
            return `This week's active adjustments: ${uniqueStrings.join(', ')}`;
        } catch {
            return null;
        }
    },

    async loadViewData(route) {
        if (!this.userId) return;

        try {
            switch (route) {
                case 'dashboard':
                    const dash = await api.getDashboard(this.userId);
                    this.dashboardData = dash;
                    DashboardComponent.render(dash);
                    break;

                case 'workout':
                    const workout = await api.getTodaysWorkout(this.userId);
                    workout.active_summary = await this.getActiveSummary(this.userId);
                    WorkoutComponent.render(workout);
                    break;

                case 'meals':
                    const meals = await api.getTodaysMeals(this.userId);
                    meals.active_summary = await this.getActiveSummary(this.userId);
                    MealsComponent.render(meals);
                    break;

                case 'shopping':
                    try {
                        const plan = await api.getCurrentPlan(this.userId);
                        ShoppingComponent.render(plan.shopping_list || []);
                    } catch {
                        ShoppingComponent.render([]);
                    }
                    break;

                case 'progress':
                    const history = await api.getWeightHistory(this.userId);
                    ProgressComponent.render(history);
                    break;

                case 'trends':
                    const trends = await api.getTrends(this.userId);
                    TrendsComponent.render(trends);
                    break;

            }
        } catch (err) {
            console.error(`Failed to load ${route}:`, err);
        }
    },

    async generatePlan() {
        if (!this.userId) return;
        try {
            const btn = document.getElementById('btn-start-workout');
            if (btn) {
                btn.textContent = 'Generating...';
                btn.disabled = true;
            }
            await api.generateWeeklyPlan(this.userId);
            this.loadViewData('dashboard');
        } catch (err) {
            alert('Plan generation failed: ' + err.message);
        }
    },

    async completeWorkout() {
        if (!this.userId) return;
        try {
            await api.logWorkout(this.userId, {
                date: new Date().toISOString(),
                exercises_completed: [],
                completion_pct: 1.0,
            });
            this.loadViewData('dashboard');
            Router.navigate('dashboard');
        } catch (err) {
            alert('Failed to log workout: ' + err.message);
        }
    },

    async handleWeightLog(e) {
        e.preventDefault();
        const form = e.target;
        const weightLbs = parseFloat(form['weight-lbs'].value);
        const weightKg = this.lbsToKg(weightLbs);
        const notes = form.notes.value;

        try {
            const btn = form.querySelector('button');
            btn.textContent = 'Logging...';
            btn.disabled = true;

            await api.logWeight(this.userId, weightKg, notes);

            // Trigger adaptive replan
            try {
                await api.replan(this.userId);
            } catch (replanErr) {
                console.error('Adaptive replan failed:', replanErr);
                // We don't alert here, just proceed with dashboard refresh
            }

            // Close modal and refresh
            document.getElementById('weight-modal').style.display = 'none';

            this.loadViewData('dashboard');

            // Reset form
            form.reset();
            btn.textContent = 'Log Weight ✓';
            btn.disabled = false;
        } catch (err) {
            alert('Weight log failed: ' + err.message);
            const btn = form.querySelector('button');
            btn.textContent = 'Log Weight ✓';
            btn.disabled = false;
        }
    },

    async handleMealLog(e) {
        e.preventDefault();
        const form = e.target;
        const btn = form.querySelector('button');

        const mealType = form.meal_type.value;
        const mealName = form.name.value;
        const notes = form.notes.value || null;

        try {
            btn.textContent = 'Estimating macros...';
            btn.disabled = true;

            // Step 1: Get AI macro estimation
            const macros = await api.estimateMacros(mealName, mealType, notes);

            btn.textContent = 'Logging...';

            // Step 2: Log the meal with estimated macros
            const data = {
                meal_type: mealType,
                name: mealName,
                calories: macros.calories,
                protein_g: macros.protein_g,
                carbs_g: macros.carbs_g,
                fat_g: macros.fat_g,
                notes: notes ? `${notes} | AI: ${macros.ai_notes}` : `AI: ${macros.ai_notes}`,
                is_planned: false,
            };

            await api.logMeal(this.userId, data);

            // Close modal and refresh
            document.getElementById('meal-modal').style.display = 'none';
            this.loadViewData('meals');

            // Reset form
            form.reset();
            btn.textContent = 'Log Meal ✓';
            btn.disabled = false;
        } catch (err) {
            alert('Meal log failed: ' + err.message);
            btn.textContent = 'Log Meal ✓';
            btn.disabled = false;
        }
    },

    showMealModal() {
        document.getElementById('meal-modal').style.display = 'flex';
    },

    async showRevisionHistory() {
        if (!this.userId) return;
        const modal = document.getElementById('revision-modal');
        const list = document.getElementById('revision-list');
        list.innerHTML = '<div class="spinner"></div>';
        modal.style.display = 'flex';

        try {
            const revisions = await api.getUserRevisions(this.userId, 20);

            if (!revisions || revisions.length === 0) {
                list.innerHTML = '<div class="empty-state">No plan adjustments yet.</div>';
                return;
            }

            list.innerHTML = revisions.map(rev => {
                const statusConfig = DashboardComponent._getStatusConfig(rev.status);
                const isTerminal = ['reverted', 'superseded', 'blocked'].includes(rev.status);
                const areaLabel = DashboardComponent._formatAreaLabel(rev.target_area);
                const timeStr = new Date(rev.created_at).toLocaleString();
                const triggerLabel = (rev.trigger || '').replace(/_/g, ' ');

                return `
                    <div class="card revision-card ${isTerminal ? 'revision-terminal' : ''}" style="margin-bottom:12px; padding:16px; ${isTerminal ? 'opacity:0.6;' : ''}">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; flex-wrap:wrap;">
                            <span class="card-badge" style="background:${statusConfig.bgColor}; color:${statusConfig.color}; font-size:11px; padding:2px 8px; border-radius:8px;">
                                ${statusConfig.icon} ${statusConfig.label}
                            </span>
                            ${areaLabel ? `<span style="font-size:11px; color:var(--text-tertiary); background:rgba(255,255,255,0.05); padding:2px 6px; border-radius:6px;">${areaLabel}</span>` : ''}
                            <span style="font-size:11px; color:var(--text-tertiary); margin-left:auto;">${timeStr}</span>
                        </div>
                        <div style="font-size:14px; color:var(--text-primary); font-weight:600; margin-bottom:4px; text-transform:capitalize;">${triggerLabel}</div>
                        <div style="font-size:13px; color:var(--text-secondary); line-height:1.4;">${rev.reason}</div>
                        ${rev.status_reason ? `<div style="font-size:12px; color:${statusConfig.color}; margin-top:6px; font-style:italic;">${rev.status_reason}</div>` : ''}
                        ${rev.status_label && isTerminal ? `<div style="font-size:12px; color:${statusConfig.color}; margin-top:4px;">${rev.status_label}</div>` : ''}
                    </div>
                `;
            }).join('');
        } catch (err) {
            list.innerHTML = `<div class="error">Failed to load history: ${err.message}</div>`;
        }
    }


};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
