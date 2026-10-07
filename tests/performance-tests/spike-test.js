import { journey, phaseAt, thresholds } from './utils/workload.js';
export { setup, teardown } from './utils/workload.js';
export { handleSummary } from './utils/summary.js';
const timeline = [{"until": 10, "name": "warmup"}, {"until": 30, "name": "normal"}, {"until": 31, "name": "spike_up"}, {"until": 51, "name": "peak"}, {"until": 52, "name": "spike_down"}, {"until": 62, "name": "recovery_00"}, {"until": 72, "name": "recovery_01"}, {"until": 82, "name": "recovery_02"}, {"until": 92, "name": "recovery_03"}, {"until": 102, "name": "recovery_04"}, {"until": 112, "name": "recovery_05"}, {"until": 122, "name": "cooldown"}];
export const options = {
  scenarios: { users: { executor: 'ramping-vus', startVUs: 0, stages: [{"duration": "10s", "target": 25}, {"duration": "20s", "target": 25}, {"duration": "1s", "target": 1000}, {"duration": "20s", "target": 1000}, {"duration": "1s", "target": 25}, {"duration": "60s", "target": 25}, {"duration": "10s", "target": 0}],
    gracefulRampDown: '10s', gracefulStop: '15s' } },
  thresholds: thresholds(["normal", "peak", "recovery_00", "recovery_01", "recovery_02", "recovery_03", "recovery_04", "recovery_05"]),
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};
export default function(data) { journey(data, phaseAt(timeline)); }
