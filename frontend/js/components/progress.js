/**
 * AI Fitness Coach v1 — Progress Component
 */
const ProgressComponent = {
    // Convert kg to lbs for display
    kgToLbs(kg) { return kg * 2.20462; },

    async render(data) {
        const container = document.getElementById('progress-content');
        if (!data || !data.weight_entries || data.weight_entries.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📊</div>
                    <div class="empty-title">No weight data yet</div>
                    <div class="empty-subtitle">Tap "Weight (lbs) +" on the dashboard to log your first entry</div>
                </div>`;
            return;
        }

        const weights = [...data.weight_entries].reverse(); // Chronological for chart (copy to avoid mutating)
        const revisions = data.revisions || [];

        // 1. Calculate Stats in lbs (with safe defaults)
        const currentWeightKg = weights.length > 0 ? weights[weights.length - 1].weight_kg : null;
        const startWeightKg = weights.length > 0 ? weights[0].weight_kg : null;
        const totalChangeLbs = (currentWeightKg !== null && startWeightKg !== null)
            ? this.kgToLbs(currentWeightKg - startWeightKg).toFixed(1) : '--';

        // 7-day average (simple version for v1)
        const avg7 = this.calculateRollingAverage(weights, 7);
        const currentAvgLbs = avg7.length > 0 ? this.kgToLbs(avg7[avg7.length - 1].value).toFixed(1) : '--';

        const displayWeight = currentWeightKg !== null ? this.kgToLbs(currentWeightKg).toFixed(1) : '--';
        const displayChange = totalChangeLbs !== '--' ? `${parseFloat(totalChangeLbs) > 0 ? '+' : ''}${totalChangeLbs}` : '--';

        container.innerHTML = `
            <div class="card" style="margin-bottom:16px">
                <div class="card-header"><span class="card-label">Biometric Progress</span></div>
                <div class="stat-row" style="margin-bottom:16px">
                    <div class="stat-item"><span class="stat-value">${displayWeight} lbs</span><span class="stat-label">Current</span></div>
                    <div class="stat-item"><span class="stat-value">${currentAvgLbs} lbs</span><span class="stat-label">7D Avg</span></div>
                    <div class="stat-item"><span class="stat-value">${displayChange} lbs</span><span class="stat-label">Total Change</span></div>
                </div>
            </div>

            <div class="card" style="margin-bottom:16px">
                <div class="card-header">
                    <span class="card-label">Weight Trend</span>
                    <span class="card-badge">Coach Audit</span>
                </div>
                <div class="chart-container" id="weight-trend-chart">
                    ${this.generateChartSVG(weights, avg7, revisions)}
                </div>
                <div style="display:flex;gap:16px;font-size:11px;color:var(--text-tertiary);justify-content:center">
                    <span style="display:flex;align-items:center;gap:4px"><i style="width:8px;height:8px;background:var(--accent-blue);border-radius:50%"></i> Weight</span>
                    <span style="display:flex;align-items:center;gap:4px"><i style="width:8px;height:2px;background:var(--accent-purple);opacity:0.6"></i> 7D Avg</span>
                    <span style="display:flex;align-items:center;gap:4px"><i style="width:2px;height:8px;background:var(--accent-purple)"></i> Plan Rev</span>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><span class="card-label">Manual Audit Log</span></div>
                <div class="revision-history-list">
                    ${weights.slice().reverse().map(w => `
                        <div class="upcoming-item" style="margin-bottom:8px">
                            <div class="upcoming-day">${new Date(w.date).toLocaleDateString(undefined, {month:'short', day:'numeric'})}</div>
                            <div class="upcoming-focus">${this.kgToLbs(w.weight_kg).toFixed(1)} lbs <span style="font-size:12px;color:var(--text-tertiary);margin-left:8px">${w.notes || ''}</span></div>
                        </div>
                    `).join('')}
                </div>
            </div>`;
    },

    calculateRollingAverage(data, windowSize) {
        let result = [];
        for (let i = 0; i < data.length; i++) {
            const window = data.slice(Math.max(0, i - windowSize + 1), i + 1);
            const sum = window.reduce((acc, val) => acc + val.weight_kg, 0);
            result.push({ date: data[i].date, value: sum / window.length });
        }
        return result;
    },

    generateChartSVG(weights, avgs, revisions) {
        if (weights.length < 2) {
            return `<div class="empty-state" style="padding:40px 0">Need at least 2 logs for trend.</div>`;
        }

        const width = 1000;
        const height = 240;
        const padding = 40;

        const allValues = [...weights.map(w => w.weight_kg), ...avgs.map(a => a.value)];
        const minW = Math.min(...allValues) - 1;
        const maxW = Math.max(...allValues) + 1;
        const range = maxW - minW;

        const getX = (idx) => padding + (idx * (width - 2 * padding) / (weights.length - 1));
        const getY = (val) => height - padding - ((val - minW) / range * (height - 2 * padding));

        const weightPath = weights.map((w, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(w.weight_kg)}`).join(' ');
        const avgPath = avgs.map((a, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(a.value)}`).join(' ');

        // Markers for revisions
        const revMarkers = revisions.map(rev => {
            const revDate = new Date(rev.date).getTime();
            // Find closest weight index for positioning on X axis
            let closestIdx = 0;
            let minDiff = Infinity;
            weights.forEach((w, i) => {
                const diff = Math.abs(new Date(w.date).getTime() - revDate);
                if (diff < minDiff) { minDiff = diff; closestIdx = i; }
            });
            
            const x = getX(closestIdx);
            // Extract label from patch
            let label = 'Plan Upd';
            if (rev.patch?.nutrition?.calorie_adjust) {
                const cal = rev.patch.nutrition.calorie_adjust;
                label = `${cal > 0 ? '+' : ''}${cal} kcal`;
            } else if (rev.patch?.workout?.volume_adjust) {
                const vol = Math.round(rev.patch.workout.volume_adjust * 100);
                label = `${vol > 0 ? '+' : ''}${vol}% vol`;
            }

            return `
                <div class="revision-marker" style="left:${(x / width) * 100}%; height:${height - padding}px">
                    <span class="revision-label" title="${rev.reason}">${label}</span>
                </div>`;
        }).join('');

        return `
            <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
                <!-- Grid lines -->
                <line x1="${padding}" y1="${getY(minW + range/2)}" x2="${width-padding}" y2="${getY(minW + range/2)}" class="chart-y-axis" />
                
                <path d="${avgPath}" class="chart-line-avg" />
                <path d="${weightPath}" class="chart-line-weight" />
                
                ${weights.map((w, i) => `<circle cx="${getX(i)}" cy="${getY(w.weight_kg)}" r="4" class="chart-point" />`).join('')}
            </svg>
            ${revMarkers}`;
    }

};
