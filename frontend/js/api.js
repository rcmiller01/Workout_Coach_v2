/**
 * AI Fitness Coach v1 — API Client
 *
 * All endpoints require JWT auth (injected automatically).
 * User identity comes from the token — no user_id params needed.
 */
const API_BASE = '/api';

const api = {
    /**
     * Make an API request with JWT auth.
     */
    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };

        const token = Auth.getAccessToken();
        if (token) {
            opts.headers['Authorization'] = `Bearer ${token}`;
        }

        if (body) opts.body = JSON.stringify(body);

        try {
            let res = await fetch(`${API_BASE}${path}`, opts);

            // Auto-refresh on 401
            if (res.status === 401 && token) {
                const refreshed = await Auth.refreshTokens();
                if (refreshed) {
                    opts.headers['Authorization'] = `Bearer ${Auth.getAccessToken()}`;
                    res = await fetch(`${API_BASE}${path}`, opts);
                } else {
                    Auth.clearTokens();
                    window.location.reload();
                    throw new Error('Session expired');
                }
            }

            if (res.status === 429) {
                const error = await res.json().catch(() => ({}));
                throw new Error(error.detail || 'Rate limit exceeded. Please wait and try again.');
            }

            if (!res.ok) {
                const error = await res.json().catch(() => ({ detail: res.statusText }));
                let errorMsg;
                if (Array.isArray(error.detail)) {
                    errorMsg = error.detail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ');
                } else {
                    errorMsg = error.detail || `HTTP ${res.status}`;
                }
                throw new Error(errorMsg);
            }
            if (res.status === 204) return null;
            return await res.json();
        } catch (err) {
            console.error(`API ${method} ${path} failed:`, err);
            throw err;
        }
    },

    // ── Auth ──
    getMe() {
        return this.request('GET', '/auth/me');
    },

    // ── Dashboard ──
    getDashboard() {
        return this.request('GET', '/dashboard/dashboard');
    },

    // ── Profile ──
    createProfile(data) {
        return this.request('POST', '/profile/', data);
    },
    getProfile() {
        return this.request('GET', '/profile/me');
    },
    updateProfile(data) {
        return this.request('PUT', '/profile/me', data);
    },
    logWeight(weightKg, notes = null) {
        return this.request('POST', '/profile/weight', {
            weight_kg: weightKg,
            notes: notes
        });
    },
    getWeightHistory() {
        return this.request('GET', '/profile/weight/history');
    },

    // ── Planning ──
    generateWeeklyPlan(options = {}) {
        return this.request('POST', '/planning/weekly', options);
    },
    getCurrentPlan() {
        return this.request('GET', '/planning/current');
    },
    replan() {
        return this.request('POST', '/planning/replan');
    },
    approveReplan(revisionId) {
        return this.request('POST', `/planning/replan/approve/${revisionId}`);
    },
    undoReplan(revisionId) {
        return this.request('POST', `/planning/replan/undo/${revisionId}`);
    },
    getRevisions(planId) {
        return this.request('GET', `/planning/revisions/${planId}`);
    },
    getUserRevisions(limit = 20) {
        return this.request('GET', `/planning/revisions/user?limit=${limit}`);
    },

    // ── Workouts ──
    getTodaysWorkout() {
        return this.request('GET', '/workouts/today');
    },
    logWorkout(data) {
        return this.request('POST', '/workouts/log', data);
    },
    addExerciseToLog(logId, data) {
        return this.request('POST', `/workouts/log/${logId}/exercise`, data);
    },
    deleteExerciseFromLog(logId, exerciseIndex) {
        return this.request('DELETE', `/workouts/log/${logId}/exercise/${exerciseIndex}`);
    },
    deleteWorkoutLog(logId) {
        return this.request('DELETE', `/workouts/log/${logId}`);
    },
    getWorkoutHistory() {
        return this.request('GET', '/workouts/history');
    },

    // ── Meals ──
    getTodaysMeals() {
        return this.request('GET', '/meals/today');
    },
    getMealPlan() {
        return this.request('GET', '/meals/plan');
    },
    importRecipe(url) {
        return this.request('POST', '/meals/import-recipe', { url });
    },
    logMeal(data) {
        return this.request('POST', '/meals/log', data);
    },
    estimateMacros(mealName, mealType, notes = null) {
        return this.request('POST', '/meals/estimate-macros', {
            meal_name: mealName,
            meal_type: mealType,
            notes: notes
        });
    },
    deleteMealLog(mealId) {
        return this.request('DELETE', `/meals/log/${mealId}`);
    },
    getMealHistory(date = null) {
        let path = '/meals/history';
        if (date) path += `?date=${date}`;
        return this.request('GET', path);
    },

    // ── Health ──
    healthCheck() {
        return this.request('GET', '/health');
    },

    // ── Review & Trends ──
    getWeeklyReview(weekOffset = 0) {
        return this.request('GET', `/review/weekly?week_offset=${weekOffset}`);
    },
    getTrends() {
        return this.request('GET', '/review/trends');
    },
};
