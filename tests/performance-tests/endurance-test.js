import { journey, phaseAt, thresholds } from './utils/workload.js';
export { setup, teardown } from './utils/workload.js';
export { handleSummary } from './utils/summary.js';
const timeline = [{"until": 60, "name": "minute_00"}, {"until": 120, "name": "minute_01"}, {"until": 180, "name": "minute_02"}, {"until": 240, "name": "minute_03"}, {"until": 300, "name": "minute_04"}, {"until": 360, "name": "minute_05"}, {"until": 420, "name": "minute_06"}, {"until": 480, "name": "minute_07"}, {"until": 540, "name": "minute_08"}, {"until": 600, "name": "minute_09"}, {"until": 660, "name": "minute_10"}, {"until": 720, "name": "minute_11"}, {"until": 780, "name": "minute_12"}, {"until": 840, "name": "minute_13"}, {"until": 900, "name": "minute_14"}, {"until": 960, "name": "minute_15"}, {"until": 1020, "name": "minute_16"}, {"until": 1080, "name": "minute_17"}, {"until": 1140, "name": "minute_18"}, {"until": 1200, "name": "minute_19"}, {"until": 1260, "name": "minute_20"}, {"until": 1320, "name": "minute_21"}, {"until": 1380, "name": "minute_22"}, {"until": 1440, "name": "minute_23"}, {"until": 1500, "name": "minute_24"}, {"until": 1560, "name": "minute_25"}, {"until": 1620, "name": "minute_26"}, {"until": 1680, "name": "minute_27"}, {"until": 1740, "name": "minute_28"}, {"until": 1800, "name": "minute_29"}];
export const options = {
  scenarios: { users: { executor: 'ramping-vus', startVUs: 0, stages: [{"duration": "30s", "target": 25}, {"duration": "1740s", "target": 25}, {"duration": "30s", "target": 0}],
    gracefulRampDown: '10s', gracefulStop: '15s' } },
  thresholds: thresholds(["minute_00", "minute_01", "minute_02", "minute_03", "minute_04", "minute_05", "minute_06", "minute_07", "minute_08", "minute_09", "minute_10", "minute_11", "minute_12", "minute_13", "minute_14", "minute_15", "minute_16", "minute_17", "minute_18", "minute_19", "minute_20", "minute_21", "minute_22", "minute_23", "minute_24", "minute_25", "minute_26", "minute_27", "minute_28", "minute_29"]),
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};
export default function(data) { journey(data, phaseAt(timeline)); }
