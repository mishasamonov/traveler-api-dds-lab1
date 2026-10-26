import { optionsFor, setup, journey } from './utils/workload.js';
import { summary } from './utils/summary.js';
export const options = optionsFor('stress');
export { setup };
export default function () { journey('stress'); }
export function handleSummary(data) { return summary(data, 'stress'); }

