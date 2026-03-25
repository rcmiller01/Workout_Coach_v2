/**
 * AI Fitness Coach v1 — API Client
 */
const API_BASE = '/api';

const api = {
    /**
     * Make an API request
     */
    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };

        // Inject JWT auth header if available
        const token = Auth.getAccessToken();
        if (token) {
            opts.headers['Authorization'] = `Bearer ${token}`;
        }

        if (body) opts.body = JSON.stringify(body);

        try {
            let res = await fetch(`${API_BASE}${path}`, opts);

            // Auto-refresh on 401 if we had a token
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
    getDashboard(userId) {
        return this.request('GET', `/dashboard/dashboard/${userId}`);
    },

    // ── Profile ──
    createProfile(data) {
        return this.request('POST', '/profile/', data);
    },
    getProfile(userId) {
        return this.request('GET', `/profile/${userId}`);
    },
    updateProfile(userId, data) {
        return this.request('PUT', `/profile/${userId}`, data);
    },
    logWeight(userId, weightKg, notes = null) {
        return this.request('POST', '/profile/weight', {
            user_id: userId,
            weight_kg: weightKg,
            notes: notes
        });
    },
    approveReplan(revisionId) {
        return this.request('POST', `/planning/replan/approve/${revisionId}`);
    },
    getWeightHistory(userId) {
        return this.request('GET', `/profile/weight/history/${userId}`);
    },
    undoReplan(revisionId) {
        return this.request('POST', `/planning/replan/undo/${revisionId}`);
    },



    // ── Planning ──
    generateWeeklyPlan(userId, options = {}) {
        return this.request('POST', '/planning/weekly', {
            user_id: userId,
            ...options,
        });
    },
    getCurrentPlan(userId) {
        return this.request('GET', `/planning/current/${userId}`);
    },
    getPlanHistory(userId) {
        return this.request('GET', `/planning/history/${userId}`);
    },
    replan(userId) {
        return this.request('POST', `/planning/replan?user_id=${userId}`);
    },


    // ── Workouts ──
    getTodaysWorkout(userId) {
        return this.request('GET', `/workouts/today/${userId}`);
    },
    logWorkout(userId, data) {
        return this.request('POST', `/workouts/log?user_id=${userId}`, data);
    },
    addExerciseToLog(logId, userId, data) {
        return this.request('POST', `/workouts/log/${logId}/exercise?user_id=${userId}`, data);
    },
    deleteExerciseFromLog(logId, userId, exerciseIndex) {
        return this.request('DELETE', `/workouts/log/${logId}/exercise/${exerciseIndex}?user_id=${userId}`);
    },
    deleteWorkoutLog(logId, userId) {
        return this.request('DELETE', `/workouts/log/${logId}?user_id=${userId}`);
    },
    getWorkoutHistory(userId) {
        return this.request('GET', `/workouts/history/${userId}`);
    },

    // ── Meals ──
    getTodaysMeals(userId) {
        return this.request('GET', `/meals/today/${userId}`);
    },
    getMealPlan(userId) {
        return this.request('GET', `/meals/plan/${userId}`);
    },
    importRecipe(url) {
        return this.request('POST', '/meals/import-recipe', { url });
    },
    logMeal(userId, data) {
        return this.request('POST', `/meals/log?user_id=${userId}`, data);
    },
    estimateMacros(mealName, mealType, notes = null) {
        return this.request('POST', '/meals/estimate-macros', {
            meal_name: mealName,
            meal_type: mealType,
            notes: notes
        });
    },
    deleteMealLog(userId, mealId) {
        return this.request('DELETE', `/meals/log/${mealId}?user_id=${userId}`);
    },
    getMealHistory(userId, date = null) {
        let path = `/meals/history/${userId}`;
        if (date) path += `?date=${date}`;
        return this.request('GET', path);
    },

    // ── Health ──
    healthCheck() {
        return this.request('GET', '/health');
    },

    // ── Revisions ──
    getRevisions(planId) {
        return this.request('GET', `/planning/revisions/${planId}`);
    },
    getUserRevisions(userId, limit = 20) {
        return this.request('GET', `/planning/revisions/user/${userId}?limit=${limit}`);
    },

    // ── Review & Trends ──
    getWeeklyReview(userId, weekOffset = 0) {
        return this.request('GET', `/review/weekly/${userId}?week_offset=${weekOffset}`);
    },
    getTrends(userId) {
        return this.request('GET', `/review/trends/${userId}`);
    },
};
