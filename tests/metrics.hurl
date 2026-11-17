# Laboratory 7: Prometheus metrics endpoint of TravelerAPI.

# Generate some traffic: create, read and delete one plan.
POST {{host}}/api/travel-plans
Content-Type: application/json
{
  "title": "Metrics Test Plan"
}

HTTP 201
[Captures]
metrics_plan_id: jsonpath "$.id"

GET {{host}}/api/travel-plans/{{metrics_plan_id}}

HTTP 200

GET {{host}}/api/travel-plans/00000000-0000-4000-8000-000000000000

HTTP 404

# The endpoint returns the Prometheus text exposition format.
GET {{host}}/metrics

HTTP 200
[Asserts]
header "Content-Type" contains "text/plain"
# HTTP metrics use route templates, not raw URLs (bounded label values).
body matches /http_request_duration_seconds_count\{[^}]*method="POST",route="\/api\/travel-plans",status="201"[^}]*\} [1-9]/
body matches /http_request_duration_seconds_count\{[^}]*route="\/api\/travel-plans\/:id",status="404"[^}]*\} [1-9]/
body not contains "{{metrics_plan_id}}"
body contains "# TYPE http_requests_in_flight gauge"
# Per-shard database metrics, pool state and mapping version.
body matches /db_query_duration_seconds_count\{[^}]*shard="[0-9a-f]",server="[^"]+",kind="query",outcome="ok"[^}]*\} [1-9]/
body matches /db_pool_connections\{[^}]*database="db_[0-9a-f]",server="[^"]+",state="total"[^}]*\} [1-9]/
body matches /shard_mapping_version\{app="traveler-api"\} [1-9]/
body matches /shard_server_info\{[^}]*shard="f",server="[^"]+",database="db_f"[^}]*\} 1/
body matches /travel_plans_created_total\{[^}]*shard="[0-9a-f]"[^}]*\} [1-9]/
body contains "scatter_gather_duration_seconds_count"
# Default Node.js process metrics.
body contains "process_cpu_seconds_total"
body contains "nodejs_eventloop_lag_p99_seconds"

DELETE {{host}}/api/travel-plans/{{metrics_plan_id}}

HTTP 204
