/**
 * AI Fitness Coach v1 — Main Application
 */
const App = {
    userId: null,
    dashboardData: null,

    // In-flight guards for all async actions
    _busy: {},

    // Unit conversion helpers
    lbsToKg(lbs) { return lbs * 0.453592; },
    kgToLbs(kg) { return kg * 2.20462; },

    /**
     * Generic async action wrapper.
     * - Prevents duplicate calls via _busy[key]
     * - Sets button to loading state
     * - Resets button in finally (success or error)
     * - Shows error alert on failure
     *
     * @param {string} key          unique action name for dedup
     * @param {Function} asyncFn    the work to do (receives no args)
     * @param {Object} opts
     * @param {HTMLElement|string|null} opts.btn   button element, CSS selector, or null
     * @param {string} opts.loadingText            text while in-flight
     * @param {string} opts.defaultText            text to restore on error/reset
     * @param {string} opts.errorPrefix            prefix for alert message
     * @param {Function|null} opts.onSuccess       called after asyncFn resolves
     * @param {Function|null} opts.onError         called after asyncFn rejects (before alert)
     */
    async _runAction(key, asyncFn, opts = {}) {
        if (this._busy[key]) return;
        this._busy[key] = true;

        const {
            btn = null,
            loadingText = 'Working…',
            defaultText = null,
            errorPrefix = 'Action failed',
            onSuccess = null,
            onError = null,
        } = opts;

        // Resolve button element
        const btnEl = typeof btn === 'string' ? document.querySelector(btn) : btn;
        const origText = btnEl ? (defaultText || btnEl.textContent) : defaultText;

        if (btnEl) {
            btnEl.textContent = loadingText;
            btnEl.disabled = true;
            btnEl.style.opacity = '0.7';
        }

        try {
            await asyncFn();
            if (onSuccess) onSuccess();
        } catch (err) {
            if (onError) onError(err);
            alert(`${errorPrefix}: ${err.message}`);
            // Restore button on error so user can retry
            if (btnEl && btnEl.isConnected) {
                btnEl.textContent = origText || defaultText || 'Retry';
                btnEl.disabled = false;
                btnEl.style.opacity = '1';
            }
        } finally {
            this._busy[key] = false;
        }
    },

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
        const btn = form.querySelector('button');

        await this._runAction('setup', async () => {
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
        }, {
            btn,
            loadingText: 'Setting up…',
            defaultText: 'Get Started',
            errorPrefix: 'Setup failed',
        });
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

    // ── Plan Generation ──

    _setGenerateButtons(state) {
        const selectors = [
            '#btn-start-workout',
            '#btn-generate-plan',
            'button[onclick*="generatePlan"]',
        ];
        const buttons = document.querySelectorAll(selectors.join(','));
        buttons.forEach(btn => {
            if (state === 'generating') {
                btn.textContent = 'Generating…';
                btn.disabled = true;
                btn.style.opacity = '0.7';
            } else if (state === 'error') {
                btn.textContent = 'Retry Generate →';
                btn.disabled = false;
                btn.style.opacity = '1';
            } else {
                btn.textContent = 'Generate Plan →';
                btn.disabled = false;
                btn.style.opacity = '1';
            }
        });
    },

    async generatePlan() {
        if (!this.userId || this._busy.generatePlan) return;
        this._busy.generatePlan = true;
        this._setGenerateButtons('generating');
        try {
            await api.generateWeeklyPlan(this.userId);
            this.loadViewData('dashboard');
        } catch (err) {
            alert('Plan generation failed: ' + err.message);
            this._setGenerateButtons('error');
        } finally {
            this._busy.generatePlan = false;
        }
    },

    // ── Workout Completion ──

    async completeWorkout() {
        if (!this.userId) return;
        const btn = document.getElementById('btn-complete-workout');

        await this._runAction('completeWorkout', async () => {
            const { exercises, completion_pct } = WorkoutComponent.collectWorkoutData();
            await api.logWorkout(this.userId, {
                date: new Date().toISOString(),
                exercises_completed: exercises,
                completion_pct,
            });
            WorkoutComponent._adhocExercises = [];
            this.loadViewData('dashboard');
            Router.navigate('dashboard');
        }, {
            btn,
            loadingText: 'Logging & syncing…',
            defaultText: 'Complete Workout ✓',
            errorPrefix: 'Failed to log workout',
        });
    },

    // ── Weight Logging ──

    async handleWeightLog(e) {
        e.preventDefault();
        const form = e.target;
        const weightLbs = parseFloat(form['weight-lbs'].value);
        const weightKg = this.lbsToKg(weightLbs);
        const notes = form.notes.value;
        const btn = form.querySelector('button');

        await this._runAction('weightLog', async () => {
            await api.logWeight(this.userId, weightKg, notes);

            // Trigger adaptive replan (non-critical)
            try {
                await api.replan(this.userId);
            } catch (replanErr) {
                console.error('Adaptive replan failed:', replanErr);
            }

            // Close modal and refresh
            document.getElementById('weight-modal').style.display = 'none';
            this.loadViewData('dashboard');
            form.reset();
        }, {
            btn,
            loadingText: 'Logging…',
            defaultText: 'Log Weight ✓',
            errorPrefix: 'Weight log failed',
        });
    },

    // ── Meal Logging (custom via modal) ──

    async handleMealLog(e) {
        e.preventDefault();
        const form = e.target;
        const btn = form.querySelector('button');

        const mealType = form.meal_type.value;
        const mealName = form.name.value;
        const notes = form.notes.value || null;

        await this._runAction('mealLog', async () => {
            // Step 1: AI macro estimation
            if (btn && btn.isConnected) btn.textContent = 'Estimating macros…';
            const macros = await api.estimateMacros(mealName, mealType, notes);

            // Step 2: Log the meal
            if (btn && btn.isConnected) btn.textContent = 'Logging…';
            await api.logMeal(this.userId, {
                meal_type: mealType,
                name: mealName,
                calories: macros.calories,
                protein_g: macros.protein_g,
                carbs_g: macros.carbs_g,
                fat_g: macros.fat_g,
                notes: notes ? `${notes} | AI: ${macros.ai_notes}` : `AI: ${macros.ai_notes}`,
                is_planned: false,
            });

            // Close modal and refresh
            document.getElementById('meal-modal').style.display = 'none';
            this.loadViewData('meals');
            form.reset();
        }, {
            btn,
            loadingText: 'Estimating macros…',
            defaultText: 'Log Meal ✓',
            errorPrefix: 'Meal log failed',
        });
    },

    // ── Planned Meal Logging ──

    async logPlannedMeal(encodedData) {
        // Find the clicked button to provide visual feedback
        const key = 'logPlanned_' + encodedData.substring(0, 20);
        if (this._busy[key]) return;

        // Find the button that triggered this (via onclick attribute match)
        const allBtns = document.querySelectorAll('button[onclick*="logPlannedMeal"]');
        let clickedBtn = null;
        allBtns.forEach(b => {
            if (b.getAttribute('onclick')?.includes(encodedData.substring(0, 30))) {
                clickedBtn = b;
            }
        });

        await this._runAction(key, async () => {
            const meal = JSON.parse(decodeURIComponent(encodedData));
            await api.logMeal(this.userId, {
                meal_type: meal.meal_type,
                name: meal.name,
                calories: meal.calories,
                protein_g: meal.protein_g,
                carbs_g: meal.carbs_g,
                fat_g: meal.fat_g,
                notes: 'Logged from plan',
                is_planned: true,
            });
            this.loadViewData('meals');
        }, {
            btn: clickedBtn,
            loadingText: 'Logging…',
            defaultText: '✓ Log as Eaten',
            errorPrefix: 'Failed to log meal',
        });
    },

    // ── Meal Deletion ──

    async deleteMealLog(mealId) {
        if (!confirm('Remove this logged meal?')) return;

        // Find the delete button for this meal
        const deleteBtn = document.querySelector(`button[onclick*="deleteMealLog('${mealId}')"]`);

        await this._runAction('deleteMeal_' + mealId, async () => {
            await api.deleteMealLog(this.userId, mealId);
            this.loadViewData('meals');
        }, {
            btn: deleteBtn,
            loadingText: '…',
            defaultText: '✕',
            errorPrefix: 'Failed to delete meal',
        });
    },

    // ── Modals ──

    showMealModal() {
        document.getElementById('meal-modal').style.display = 'flex';
    },

    // ── Revision History ──

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
