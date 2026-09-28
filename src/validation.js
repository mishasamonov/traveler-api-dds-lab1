class ApiError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

const bad = message => { throw new ApiError(400, `Validation error: ${message}`); };
const planFields = new Set(['title', 'description', 'start_date', 'end_date', 'budget', 'currency', 'is_public']);
const locationFields = new Set(['name', 'address', 'latitude', 'longitude', 'arrival_date', 'departure_date', 'budget', 'notes', 'visit_order']);
const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

function date(value, timestamp) {
  if (typeof value !== 'string') return false;
  if (!timestamp && !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  if (timestamp && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return false;
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  const check = new Date(Date.UTC(year, month - 1, day));
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) return false;
  if (!timestamp) return true;
  const hour = Number(value.slice(11, 13)), minute = Number(value.slice(14, 16)), second = Number(value.slice(17, 19));
  return hour <= 23 && minute <= 59 && second <= 59 && !Number.isNaN(Date.parse(value));
}

function money(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 99999999.99 &&
    Math.abs(value * 100 - Math.round(value * 100)) < 1e-6;
}

function validate(body, kind, update = false) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) bad('JSON object required');
  const allowed = kind === 'plan' ? planFields : locationFields;
  const fields = { ...body };
  if (update) {
    if (!Number.isSafeInteger(fields.version) || fields.version < 1) bad('version must be a positive integer');
    delete fields.version;
  }
  for (const [key, value] of Object.entries(fields)) {
    if (!allowed.has(key) || (kind === 'location' && !update && key === 'visit_order')) bad(`unknown field ${key}`);
    if (key === 'title' || key === 'name') {
      if (typeof value !== 'string' || !value.trim() || value.length > 200) bad(`${key} must be 1-200 non-blank characters`);
    } else if (['description', 'address', 'notes'].includes(key)) {
      if (value !== null && typeof value !== 'string') bad(`${key} must be text`);
    } else if (key === 'start_date' || key === 'end_date' || key === 'arrival_date' || key === 'departure_date') {
      if (value !== null && !date(value, key.endsWith('_date') && kind === 'location')) bad(`${key} has an invalid date`);
    } else if (key === 'budget') {
      if (value !== null && !money(value)) bad('budget must be a non-negative number with 2 decimal places');
    } else if (key === 'currency') {
      if (typeof value !== 'string' || !/^[A-Z]{3}$/.test(value)) bad('currency must have 3 uppercase letters');
    } else if (key === 'is_public') {
      if (typeof value !== 'boolean') bad('is_public must be boolean');
    } else if (key === 'latitude' || key === 'longitude') {
      const max = key === 'latitude' ? 90 : 180;
      if (value !== null && (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > max)) bad(`${key} out of range`);
    } else if (key === 'visit_order') {
      if (!Number.isSafeInteger(value) || value < 1) bad('visit_order must be a positive integer');
    }
  }
  if (!update && (!fields[kind === 'plan' ? 'title' : 'name'])) bad(`${kind === 'plan' ? 'title' : 'name'} required`);
  const first = kind === 'plan' ? 'start_date' : 'arrival_date';
  const last = kind === 'plan' ? 'end_date' : 'departure_date';
  if (fields[first] && fields[last] && new Date(fields[last]) < new Date(fields[first])) bad(`${last} before ${first}`);
  return fields;
}

function checkCombinedDates(fields, previous, kind) {
  const first = kind === 'plan' ? 'start_date' : 'arrival_date';
  const last = kind === 'plan' ? 'end_date' : 'departure_date';
  const a = Object.hasOwn(fields, first) ? fields[first] : previous[first];
  const b = Object.hasOwn(fields, last) ? fields[last] : previous[last];
  if (a && b && new Date(b) < new Date(a)) bad(`${last} before ${first}`);
}

module.exports = { ApiError, validate, checkCombinedDates, uuid };
