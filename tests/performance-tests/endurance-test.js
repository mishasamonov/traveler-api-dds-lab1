import { optionsFor, setup, journey } from './utils/workload.js';
import { summary } from './utils/summary.js';
export const options = optionsFor('endurance');
export { setup };
export default function () { journey('endurance'); }
export function handleSummary(data) { return summary(data, 'endurance'); }

