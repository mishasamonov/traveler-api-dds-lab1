// Laboratory 8: travel plan documents (plan_documents.doc, JSONB).
// The REST API keeps the shape of laboratories 2-7: same fields, same order,
// same number and date formats, so clients do not see the storage change.

// The relational columns were NUMERIC(10,6)/NUMERIC(11,6): coordinates keep 6 decimals.
const coordinate = v => (v == null ? v : Math.round(v * 1e6) / 1e6);
// TIMESTAMPTZ values are kept as ISO strings in UTC.
const timestamp = v => (v == null ? null : new Date(v).toISOString());

const PLAN_DEFAULTS = { description: null, start_date: null, end_date: null, budget: null, currency: 'USD', is_public: false };
const LOCATION_DEFAULTS = { address: null, latitude: null, longitude: null, arrival_date: null, departure_date: null, budget: null, notes: null };

function locationPatch(fields) {
  const patch = { ...fields };
  for (const key of ['latitude', 'longitude']) if (key in patch) patch[key] = coordinate(patch[key]);
  for (const key of ['arrival_date', 'departure_date']) if (key in patch) patch[key] = timestamp(patch[key]);
  return patch;
}

const planPatch = fields => ({ ...fields });
// New document: every key is present (the CHECK plan_document_valid requires it).
const planDocument = fields => ({ title: fields.title, ...PLAN_DEFAULTS, ...planPatch(fields), locations: [] });
// visit_order and created_at are added by the UPDATE that appends the location.
const locationDocument = (id, fields) => ({ id, ...LOCATION_DEFAULTS, ...locationPatch(fields), version: 1 });

function planOut(row, withLocations = false) {
  const d = row.doc;
  const plan = {
    id: row.id, title: d.title, description: d.description, start_date: d.start_date, end_date: d.end_date,
    budget: d.budget, currency: d.currency, is_public: d.is_public,
    version: row.version, created_at: row.created_at, updated_at: row.updated_at,
  };
  if (withLocations) plan.locations = d.locations.map(l => locationOut(l, row.id));
  return plan;
}

function locationOut(l, planId) {
  return {
    id: l.id, travel_plan_id: planId, name: l.name, address: l.address, latitude: l.latitude, longitude: l.longitude,
    visit_order: l.visit_order, arrival_date: timestamp(l.arrival_date), departure_date: timestamp(l.departure_date),
    budget: l.budget, notes: l.notes, version: l.version, created_at: timestamp(l.created_at),
  };
}

module.exports = { planDocument, locationDocument, planPatch, locationPatch, planOut, locationOut };
