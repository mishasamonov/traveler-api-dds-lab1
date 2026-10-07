import { journey, phaseAt, thresholds } from './utils/workload.js';
export { setup, teardown } from './utils/workload.js';
export { handleSummary } from './utils/summary.js';
const timeline = [{"until": 10, "name": "ramp_25"}, {"until": 30, "name": "hold_25"}, {"until": 40, "name": "ramp_100"}, {"until": 60, "name": "hold_100"}, {"until": 70, "name": "ramp_250"}, {"until": 90, "name": "hold_250"}, {"until": 100, "name": "ramp_500"}, {"until": 120, "name": "hold_500"}, {"until": 130, "name": "ramp_1000"}, {"until": 150, "name": "hold_1000"}, {"until": 160, "name": "ramp_2000"}, {"until": 180, "name": "hold_2000"}, {"until": 190, "name": "ramp_recovery"}, {"until": 220, "name": "recovery"}, {"until": 230, "name": "cooldown"}];
export const options = {
  scenarios: { users: { executor: 'ramping-vus', startVUs: 0, stages: [{"duration": "10s", "target": 25}, {"duration": "20s", "target": 25}, {"duration": "10s", "target": 100}, {"duration": "20s", "target": 100}, {"duration": "10s", "target": 250}, {"duration": "20s", "target": 250}, {"duration": "10s", "target": 500}, {"duration": "20s", "target": 500}, {"duration": "10s", "target": 1000}, {"duration": "20s", "target": 1000}, {"duration": "10s", "target": 2000}, {"duration": "20s", "target": 2000}, {"duration": "10s", "target": 25}, {"duration": "30s", "target": 25}, {"duration": "10s", "target": 0}],
    gracefulRampDown: '10s', gracefulStop: '15s' } },
  thresholds: thresholds(["hold_25", "hold_100", "hold_250", "hold_500", "hold_1000", "hold_2000", "recovery"]),
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};
export default function(data) { journey(data, phaseAt(timeline)); }
