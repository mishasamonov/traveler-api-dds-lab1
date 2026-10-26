// Adapted from potapuff/SumDU.DDS.25F.lab2 (MIT), see instructor/.
export const BASE_URL = __ENV.API_URL || 'http://127.0.0.1:4567';
export const ENDPOINTS = {
  TRAVEL_PLANS: `${BASE_URL}/api/travel-plans`,
  TRAVEL_PLAN_BY_ID: id => `${BASE_URL}/api/travel-plans/${id}`,
  LOCATIONS_FOR_PLAN: id => `${BASE_URL}/api/travel-plans/${id}/locations`,
  LOCATION_BY_ID: id => `${BASE_URL}/api/locations/${id}`,
  HEALTH: `${BASE_URL}/health`,
};
