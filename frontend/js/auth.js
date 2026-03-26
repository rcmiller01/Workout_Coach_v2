/**
 * AI Fitness Coach — Auth Module
 *
 * Manages JWT token storage, login, register, refresh, and logout.
 */
const Auth = {
    // ── Token Storage ──

    getAccessToken()  { return localStorage.getItem('access_token'); },
    getRefreshToken() { return localStorage.getItem('refresh_token'); },
    getUserId()       { return localStorage.getItem('coach_user_id'); },
    getUsername()      { return localStorage.getItem('coach_username'); },

    saveTokens(data) {
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        localStorage.setItem('coach_user_id', data.user_id);
        localStorage.setItem('coach_username', data.username);
    },

    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('coach_user_id');
        localStorage.removeItem('coach_username');
    },

    isLoggedIn() {
        return !!this.getAccessToken();
    },

    isLegacyUser() {
        return false; // Legacy UUID mode removed — JWT required
    },

    // ── API Calls ──

    async register(username, password, email) {
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email: email || null }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
            throw new Error(err.detail || 'Registration failed');
        }
        const data = await res.json();
        this.saveTokens(data);
        return data;
    },

    async login(username, password) {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Login failed' }));
            throw new Error(err.detail || 'Login failed');
        }
        const data = await res.json();
        this.saveTokens(data);
        return data;
    },

    async refreshTokens() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) return false;

        try {
            const res = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            if (!res.ok) return false;
            const data = await res.json();
            this.saveTokens(data);
            return true;
        } catch {
            return false;
        }
    },

    async claimAccount(username, password) {
        const res = await fetch('/api/auth/set-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Claim failed' }));
            throw new Error(err.detail || 'Claim failed');
        }
        const data = await res.json();
        this.saveTokens(data);
        return data;
    },

    logout() {
        this.clearTokens();
        window.location.reload();
    },
};
