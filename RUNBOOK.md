# SRE Runbook

Operational runbook for the serverless health-check API. It intentionally references only signals and controls implemented by this repository; no external paging or incident-management integration is assumed.

## 1. First response

For any alert, failed deployment or user report:

1. confirm the affected environment (`staging` or `prod`);
2. verify the user path before changing infrastructure;
3. identify whether the failure is API Gateway, Lambda, DynamoDB/KMS, network or deployment-state related;
4. check the currently served immutable release alias and Git SHA;
5. prefer a reversible Git/Terraform change over a console mutation;
6. after mitigation, rerun the same user-path and live-control verification that detected the issue.

Do not run a blind repeated `terraform apply`, broad deletion, `terraform state rm`, or an unreviewed console fix.

## 2. Fast user-path checks

Set the environment-specific values from Terraform outputs and retrieve the generated API key through AWS only when authorized to do so:

```bash
API_URL="$(terraform -chdir=terraform output -raw api_url)"
API_KEY_ID="$(terraform -chdir=terraform output -raw api_key_id)"
API_KEY="$(aws apigateway get-api-key \
  --api-key "${API_KEY_ID}" \
  --include-value \
  --query value \
  --output text)"
```

Read-only liveness:

```bash
curl -i \
  -H "x-api-key: ${API_KEY}" \
  "${API_URL}/health"
```

Expected: HTTP `200`, `status=healthy`, and the deployed Git SHA in `version`.

Write path:

```bash
curl -i \
  -X POST \
  -H "x-api-key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"payload":"runbook-check"}' \
  "${API_URL}/health"
```

Expected: HTTP `200`, the required success JSON, and `X-Request-Id`.

Do not use repeated POST requests as a health probe; they intentionally create DynamoDB records.

## 3. Confirm the release being served

The API must use the environment release alias and a published numeric Lambda version, never `$LATEST`.

```bash
ENVIRONMENT="staging"
FUNCTION_NAME="${ENVIRONMENT}-health-check-function"
ALIAS_NAME="${ENVIRONMENT}-release"

aws lambda get-alias \
  --function-name "${FUNCTION_NAME}" \
  --name "${ALIAS_NAME}"

aws lambda get-function-configuration \
  --function-name "${FUNCTION_NAME}" \
  --qualifier "${ALIAS_NAME}"
```

Check:

- alias name is exactly `${ENVIRONMENT}-release`;
- `FunctionVersion` is a positive number;
- `Version` matches the alias target;
- `Environment.Variables.APP_VERSION` is the expected Git commit.

The deployment workflow performs these checks automatically with `scripts/verify_release_alias.py` and also audits the live alias invoke policy.

## 4. CloudWatch signals

Implemented alarms:

| Signal | Alarm | Initial interpretation |
| --- | --- | --- |
| Lambda errors | `${env}-health-check-function-errors` | unhandled/runtime/DynamoDB/configuration failure occurred |
| Lambda throttles | `${env}-health-check-function-throttles` | reserved concurrency was exhausted |
| API Gateway 5XX | `${env}-health-check-api-5xx` | server-side API/integration failure |
| API Gateway p95 latency | `${env}-health-check-api-latency` | latency exceeded the environment threshold for two periods |

The dashboard is `${env}-health-check-dashboard`.

There is deliberately no SNS/pager target in this homework. `actions_enabled=false` avoids pretending an on-call integration exists.

## 5. Lambda error investigation

Start with the user path and current release identity, then inspect the explicit log group:

```bash
aws logs tail "${ENVIRONMENT}-health-check-function-logs" \
  --since 15m
```

Look for structured events:

- `incoming_request` — sanitized request evidence;
- `request_rejected` — defensive Lambda-side validation or route rejection;
- `request_persistence_failed` — DynamoDB/configuration failure without leaking internal details to the caller;
- `request_saved` — successful write correlation ID;
- `health_check_succeeded` — read-only GET success.

If failures begin immediately after a deployment, compare `APP_VERSION` with the expected commit before changing infrastructure.

## 6. API Gateway 5XX

Check whether the failure is visible on both GET and POST:

- GET failing suggests API Gateway/Lambda/integration/runtime availability rather than DynamoDB write logic alone.
- GET healthy but POST 5XX narrows investigation toward Lambda validation/persistence, DynamoDB, KMS or VPC endpoint access.

Inspect:

1. API Gateway access log group `${env}-health-check-api-access-logs`;
2. API Gateway `5XXError`, `Latency` and `IntegrationLatency` metrics;
3. Lambda Errors/Throttles at the same timestamp;
4. current release alias and Git SHA;
5. recent reviewed deployment changes.

Do not weaken request validation or API-key enforcement as a mitigation.

## 7. High latency

Compare API Gateway `Latency` with `IntegrationLatency`:

- both high: inspect Lambda execution, throttles, DynamoDB/KMS and VPC path;
- API `Latency` high while integration latency is normal: investigate the API Gateway/request edge rather than scaling Lambda first.

Check traffic volume and throttling before increasing concurrency. Reserved concurrency is intentionally a safety boundary as well as a capacity setting.

## 8. 429 / throttling

The API has three independent limits:

1. API Gateway method/stage throttle;
2. API-key usage-plan throttle;
3. Lambda reserved concurrency.

A controlled burst returning some HTTP `429` in staging is expected and is explicitly verified by CI/CD.

If normal traffic is receiving 429s:

- check API Gateway request count and 4XX/429 timing;
- check Lambda `Throttles`;
- compare traffic to the environment tfvars;
- identify whether the increase is expected before changing limits;
- change one bounded capacity control at a time through reviewed Terraform and verify recovery.

Do not disable throttling to make a test pass.

## 9. DynamoDB / KMS write failure

The Lambda data-plane role can only call `dynamodb:PutItem` on the exact environment table. DynamoDB is accessed through the Gateway VPC Endpoint.

Check:

```bash
TABLE_NAME="$(terraform -chdir=terraform output -raw dynamodb_table_name)"
KMS_KEY_ARN="$(terraform -chdir=terraform output -raw kms_key_arn)"

aws dynamodb describe-table --table-name "${TABLE_NAME}"
aws dynamodb describe-continuous-backups --table-name "${TABLE_NAME}"
aws kms get-key-rotation-status --key-id "${KMS_KEY_ARN}"
```

Expected controls:

- table is active;
- SSE is enabled with the expected CMK;
- point-in-time recovery is enabled;
- TTL is configured on `expires_at`;
- CMK rotation is enabled;
- production deletion protection remains enabled.

If an IAM/KMS error appears after a policy change, fix the smallest exact permission. Do not add `Action = "*"` or an undocumented resource wildcard.

## 10. VPC/network investigation

Expected topology:

- exactly two private Lambda subnets in separate AZs;
- no public IP assignment;
- no Internet Gateway;
- no active NAT Gateway;
- security-group egress limited to HTTPS/443 toward the DynamoDB managed prefix list;
- DynamoDB Gateway VPC Endpoint in the application VPC;
- endpoint policy permits only `dynamodb:PutItem` on the exact table.

The deployment verifier checks these live. If POST fails while GET remains healthy, inspect the VPC endpoint and its route-table association before adding Internet egress.

## 11. Failed Terraform deployment

### Before apply

A failure in formatting, unit tests, Terraform tests, TFLint, IAM audit, Bandit, dependency audit, Checkov, Trivy, actionlint, zizmor or the saved-plan guard is a **deployment blocker**. Fix the underlying source or configuration. Do not bypass or disable the gate.

### During apply

If AWS creates a named object but Terraform fails before state ownership is safely recorded:

1. stop automatic retries;
2. identify the exact AWS resource and Terraform address;
3. inspect remote state;
4. reconcile/import only that intended resource if appropriate;
5. generate a fresh saved plan;
6. review the new plan before apply.

Never use broad deletion to make the next apply start from a visually clean account.

## 12. Drift detection failure

Every successful deployment ends with a second Terraform plan using the same backend, environment tfvars and application Git SHA.

If that plan returns changes:

1. treat the deployment as incomplete;
2. do not start another deployment concurrently;
3. identify whether drift is from AWS eventual consistency, a manual change or an unmanaged resource;
4. reconcile source/state intentionally;
5. rerun the plan until the expected result is zero drift.

## 13. Rollback

Preferred rollback is GitOps-based:

1. identify the last known-good Git commit;
2. revert the bad source/configuration through normal review;
3. rerun the environment deployment;
4. review the saved Terraform plan;
5. apply that exact plan;
6. verify GET/POST, DynamoDB persistence and the release alias;
7. require zero post-deployment drift.

The normal release path publishes an immutable Lambda version and moves `${env}-release`. API Gateway itself does not need to be manually repointed.

For production, keep the GitHub Environment required-reviewer gate in place during rollback unless an organization-defined emergency process explicitly says otherwise.

## 14. Post-incident record

Record at minimum:

- start/end time;
- affected environment and user path;
- impact;
- alert/signal that detected the issue;
- deployed `APP_VERSION` / Git commit;
- evidence used to isolate the fault domain;
- mitigation or rollback performed;
- verification that user impact ended;
- root cause when known;
- prevention/follow-up action.

Do not mark an incident resolved solely because an AWS resource reports `ACTIVE`; verify the client path.
