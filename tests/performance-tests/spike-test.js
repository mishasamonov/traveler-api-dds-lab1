import { optionsFor, setup, journey } from './utils/workload.js';
import { summary } from './utils/summary.js';
export const options = optionsFor('spike');
export { setup };
export default function () { journey('spike'); }
export function handleSummary(data) { return summary(data, 'spike'); }

