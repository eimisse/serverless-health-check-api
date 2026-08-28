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
| Lambda throttles | `${env}-health-check-function-throttles` | Lambda execution capacity was throttled; correlate with concurrency and traffic |
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

Check traffic volume and throttling before increasing capacity. Production has explicit Lambda reserved concurrency; staging intentionally uses the account-shared concurrency pool because a very small reservation would violate the account's minimum unreserved-concurrency requirement. In both environments, API Gateway stage and per-key usage-plan limits remain the primary request-rate controls.

## 8. 429 / throttling

The API always has two explicit API Gateway limits:

1. method/stage rate and burst limits;
2. API-key usage-plan rate and burst limits.

Production additionally has explicit Lambda reserved concurrency. Staging intentionally uses shared Lambda account concurrency while preserving the API Gateway controls.

API Gateway describes throttling limits as best-effort targets rather than hard per-request ceilings. Therefore release gating does **not** depend on one timing-sensitive burst producing a `429`. `scripts/verify_staging_release.py` deterministically reads the live stage and usage-plan control plane and verifies:

- GET and POST stage rate/burst values;
- detailed method metrics remain enabled;
- usage-plan rate/burst values;
- association with the exact deployed API/stage;
- association of the generated API key.

If normal traffic is receiving 429s:

- check API Gateway request count and 4XX/429 timing;
- check Lambda `Throttles`;
- compare traffic to the environment tfvars;
- identify whether the increase is expected before changing limits;
- change one bounded capacity control at a time through reviewed Terraform and verify recovery.

Do not disable throttling to make a test pass.

## 9. DynamoDB / KMS write failure

The Lambda data-plane role can only call `dynamodb:PutItem` on the exact environment table. DynamoDB is accessed through the Gateway VPC Endpoint. Runtime KMS use is constrained to DynamoDB and the exact table/account encryption context; `kms:CreateGrant` remains a deployment/table-lifecycle permission rather than a Lambda runtime permission.

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
- endpoint policy permits only `dynamodb:PutItem` on the exact table for the exact Lambda runtime role.

The staging release verifier checks these live. If POST fails while GET remains healthy, inspect the VPC endpoint and its route-table association before adding Internet egress.

## 11. Failed Terraform deployment

### Before apply

A failure in formatting, unit tests, Terraform tests, TFLint, IAM audit, Bandit, dependency audit, Checkov, Trivy, actionlint, zizmor, CodeQL review, deployment-role preflight or the saved-plan guard is a **deployment blocker**. Fix the underlying source or configuration. Do not bypass or disable the gate.

### During apply

If AWS creates or updates an object but Terraform fails before the operation completes:

1. stop blind/manual retries;
2. identify the exact AWS resource and Terraform address;
3. inspect the correct environment remote state;
4. determine what AWS actually changed before altering anything;
5. reconcile/import only an intended resource if state ownership was not recorded and import is appropriate;
6. generate a fresh saved plan;
7. review the new plan before any apply.

Never use broad deletion to make the next apply start from a visually clean account.

For production, the deployment workflow separately captures the pre-apply `prod-release` target. If apply starts and the workflow later fails, the fail-safe release rollback described in section 13 runs automatically when a previous release exists. That release rollback does **not** prove the rest of the partially applied infrastructure was reverted.

## 12. Drift detection failure

Every successful deployment ends with a second Terraform plan using the same backend, environment tfvars and application Git SHA.

If that plan returns changes:

1. treat the deployment as incomplete;
2. do not start another deployment concurrently;
3. identify whether drift is from AWS eventual consistency, a manual/emergency change or a partially applied resource;
4. reconcile source/state intentionally;
5. rerun the plan until the expected result is zero drift.

An emergency production alias rollback intentionally creates drift if Terraform desired state still points to the failed new release. Do not hide that drift. Correct/revert source and run the normal reviewed deployment path.

## 13. Rollback and production promotion safety

### Normal rollback

Preferred rollback is GitOps-based:

1. identify the last known-good Git commit;
2. revert the bad source/configuration through normal review;
3. rerun the environment deployment;
4. review the saved Terraform plan;
5. apply that exact plan;
6. verify GET/POST, DynamoDB persistence and the release alias;
7. require zero post-deployment drift.

The normal release path publishes an immutable Lambda version and moves `${env}-release`. API Gateway itself does not need to be manually repointed.

### Production preconditions

Production is `workflow_dispatch` only. Before the `prod` Environment/OIDC deployment job is eligible to start, the workflow requires a successful **push-triggered staging deployment for the exact same Git SHA**. The `prod` GitHub Environment should also have required reviewers configured so a human approval gate occurs before protected environment variables and the OIDC token become available.

### Automatic production release fail-safe

Immediately before Terraform planning/apply, the workflow reads the current `prod-release` alias. If it exists, it records:

- the previous numeric Lambda version;
- that version's immutable `APP_VERSION` Git SHA.

If Terraform apply starts and the deployment subsequently fails — including a partial apply failure or a post-apply verification/drift failure — the workflow attempts to restore `prod-release` to that previous numeric version. It then verifies both the restored alias version and the restored `APP_VERSION`.

This reduces the time a bad Lambda release can stay on the live alias, but it is **not** a claim of zero-impact or two-phase/canary deployment. Other Terraform resources may already have changed. After an emergency alias rollback:

1. treat the workflow as failed even if user traffic recovered;
2. preserve logs and the Terraform plan/state evidence;
3. inspect exactly which non-alias resources changed;
4. revert/fix the source through review;
5. run a fresh plan and the normal production flow;
6. require all live verification and zero drift before declaring the deployment recovered.

On an initial production deployment there is no previous alias target to restore; a failure after apply begins therefore requires direct incident recovery from Terraform/AWS evidence rather than pretending an automatic rollback is possible.

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
