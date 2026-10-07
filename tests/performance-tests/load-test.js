import { journey, phaseAt, thresholds } from './utils/workload.js';
export { setup, teardown } from './utils/workload.js';
export { handleSummary } from './utils/summary.js';
const timeline = [{"until": 15, "name": "ramp_25"}, {"until": 45, "name": "hold_25"}, {"until": 60, "name": "ramp_50"}, {"until": 90, "name": "hold_50"}, {"until": 105, "name": "ramp_100"}, {"until": 135, "name": "hold_100"}, {"until": 150, "name": "ramp_200"}, {"until": 195, "name": "hold_200"}, {"until": 210, "name": "cooldown"}];
export const options = {
  scenarios: { users: { executor: 'ramping-vus', startVUs: 0, stages: [{"duration": "15s", "target": 25}, {"duration": "30s", "target": 25}, {"duration": "15s", "target": 50}, {"duration": "30s", "target": 50}, {"duration": "15s", "target": 100}, {"duration": "30s", "target": 100}, {"duration": "15s", "target": 200}, {"duration": "45s", "target": 200}, {"duration": "15s", "target": 0}],
    gracefulRampDown: '10s', gracefulStop: '15s' } },
  thresholds: thresholds(["hold_25", "hold_50", "hold_100", "hold_200"]),
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};
export default function(data) { journey(data, phaseAt(timeline)); }
