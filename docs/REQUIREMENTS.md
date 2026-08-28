# Homework Requirement Coverage

This document maps each requested capability to the implementation and the evidence used to prove it. `Implemented` means the source/configuration exists in the repository. `Live verified in staging` means the corresponding AWS control or user path has passed the staging deployment workflow; every later `main` revision must repeat that verification before it is treated as releasable.

## Core requirements

| Requirement | Implementation | Verification / status |
| --- | --- | --- |
| All AWS infrastructure managed with Terraform | `terraform/` application root plus one-time `bootstrap/` trust/state root | `terraform validate`, native `terraform test`, TFLint, saved-plan review; live staging apply and zero-drift check passed |
| Staging and prod | `terraform/environments/staging.tfvars` and `prod.tfvars`; separate state keys and deployment roles | Terraform tests + environment-specific deployment workflows |
| `env-resource-name` naming | naming is derived from `var.environment` / locals for all customer-named application resources, subject only to AWS-enforced syntax | Terraform tests and saved-plan guard |
| DynamoDB request table | `${environment}-requests-db`, PAY_PER_REQUEST, UUID partition key | Live verified in staging by POST + exact DynamoDB `GetItem` correlation |
| DynamoDB SSE | environment-specific customer-managed KMS key | Terraform tests + live staging `DescribeTable` / key verification |
| API Gateway `/health` | Regional REST API with API-key protected GET/POST | Live verified in staging with valid and invalid HTTP requests |
| Throttling | API Gateway stage method throttling + per-key usage-plan throttling; production also has explicit Lambda reserved concurrency | Terraform tests + saved-plan guard + live staging control-plane verification of exact stage/usage-plan rate, burst, metrics, stage association and API-key association |
| Lambda | Python handler, deterministic package, explicit environment-prefixed log group | unit tests + live staging GET/POST path |
| Incoming event logging | structured event log with credential-bearing headers, query parameters and REST request-context API-key field redacted | unit tests + live CloudWatch evidence |
| Unique request ID | UUID v4 generated per POST | unit test + live response/DynamoDB correlation |
| Save request details | conditional DynamoDB `PutItem` with timestamp, TTL, metadata, payload and app version | live staging DynamoDB verification |
| Required success response | exact `status=healthy` / `Request processed and saved.` JSON | unit + live staging integration test |
| Dedicated Lambda IAM role | `runtime_iam` module | Terraform tests + wildcard policy audit |
| Least privilege runtime IAM | exact DynamoDB table `PutItem`, exact log-group writes, mandatory VPC ENI lifecycle only; KMS runtime use is limited to DynamoDB service use and exact table context, with grant administration excluded | policy tests / reviewed wildcard exceptions / live staging write path after deployment |
| Dedicated deployment role | environment-specific GitHub OIDC roles in `bootstrap/` | trust/policy tests + live staging AWS STS identity/preflight |
| CI/CD Terraform deployment | staging deploy on `main`; manual production workflow | live staging workflow passed; production remains manual-only and is not deployed for demonstration |
| Lambda dependency scanning | production dependency manifest is intentionally empty; CI audits both production and pinned development manifests | `pip-audit` security gate |
| IaC security scan before apply | Checkov + Trivy in the credential-free gate before AWS OIDC/apply | workflow ordering + CI |
| No wildcard IAM actions | repository policy rejects `Action: "*"` absolutely and rejects service-level wildcard actions | `scripts/check_iam_wildcards.py` |
| Wildcard resources only where mandatory | reviewed machine-readable exception catalogues under `security/` | `scripts/check_iam_wildcards.py` occurrence audit |
| Input validation | API Gateway JSON Schema plus duplicate Lambda validation | Terraform/unit/live integration tests |
| Missing `payload` returns 400 | strict POST model and Lambda fallback validation | unit + live negative test |
| README prerequisites | root README + `bootstrap/README.md` | reviewer-readable documentation |
| README CI/CD explanation | deployment flow and controls described in root README | reviewer-readable documentation |
| README staging instructions | bootstrap/GitHub Environment/deployment steps and tfvars usage | reviewer-readable documentation |
| README curl example | GET and POST examples use environment variables, never real API keys | reviewer-readable documentation |

## Naming convention notes

All customer-controlled **application** resource names begin with `staging-` or `prod-` wherever the AWS service accepts hyphens. This includes the Lambda function, release alias and explicit log group, API Gateway REST API and access-log group, DynamoDB table, IAM runtime role/policy, VPC, subnets, route table, security group, endpoint Name tags, alarms, dashboard, API key and usage plan.

Only service-enforced syntax is allowed to alter the literal spelling:

- API Gateway **Model** names must be alphanumeric, so the model is `stagingHealthCheckRequest` / `prodHealthCheckRequest` rather than using hyphens. The environment prefix is still first.
- KMS aliases must begin with the AWS-required `alias/` namespace; the customer-controlled body is `staging-requests-db-key` / `prod-requests-db-key`.
- AWS-generated identifiers such as REST API IDs, deployment IDs, Lambda numeric versions, VPC IDs, subnet IDs and VPC endpoint IDs are not customer-named resources.
- The one-time Terraform state backend, GitHub OIDC provider and regional API Gateway CloudWatch role are intentionally **shared bootstrap infrastructure**, not staging/prod application resources; these exceptions are documented in `bootstrap/README.md`.

## Bonus requirements

| Bonus | Status | Implementation / note |
| --- | --- | --- |
| Reusable Terraform modules | Implemented | network, runtime IAM, KMS, DynamoDB, Lambda, API Gateway, observability modules |
| Automatic Lambda packaging/versioning | Implemented and live verified in staging | deterministic `scripts/package_lambda.py`; `publish=true`; `${environment}-release` alias targets the published numeric version; API Gateway integration and invoke permissions are alias-qualified; `GITHUB_SHA` is stored as the application release identity |
| Manual approval before prod | Implemented in workflow; repository setting must be configured | `prod` GitHub Environment gate; required reviewer must be configured in GitHub Environment settings before using production |
| Customer-managed KMS key | Implemented and live verified in staging | environment-specific CMK with automatic rotation |
| Lambda in its own VPC | Implemented and live verified in staging | two private subnets in separate AZs, dedicated SG, no NAT/IGW |
| Invalid POST cannot reach Lambda | Implemented and live verified in staging | strict API Gateway request model/validator including `$default` model association; boundary probes verify invalid Content-Type and whitespace-only payload rejection before Lambda |
| API key | Implemented and live verified in staging | AWS-generated API Gateway key + usage plan; value is never committed and is masked when retrieved for verification |

## Additional SRE/security controls

- GitHub OIDC instead of static AWS deployment credentials.
- immutable GitHub repository/owner IDs and `main` ref restriction in the AWS OIDC trust policy.
- KMS-encrypted, versioned, private Terraform state with native S3 locking.
- no NAT Gateway or Internet Gateway in the Lambda VPC.
- DynamoDB Gateway VPC Endpoint with a narrow endpoint policy.
- Lambda security-group egress limited to TCP/443 to the regional AWS-managed DynamoDB prefix list.
- CloudWatch error/throttle/5XX/p95 latency alarms and dashboard.
- deterministic Lambda package hash and published immutable numeric versions.
- environment release aliases (`staging-release` / `prod-release`) keep API Gateway off unqualified `$LATEST`.
- live deployment verification resolves the release alias, requires a numeric version, and proves that version's `APP_VERSION` equals the deployed Git SHA.
- Lambda defense-in-depth route binding rejects direct/misrouted invocations outside `/health` without persistence.
- credential redaction covers sensitive headers, query-string values and `requestContext.identity.apiKey` without mutating the source event.
- DynamoDB PAY_PER_REQUEST, string partition key, PITR, TTL and production deletion protection are saved-plan invariants.
- destructive Terraform plan guard and exact saved-plan apply.
- the plan guard blocks release alias regression to `$LATEST`, unqualified API Gateway Lambda integration and loss of alias-qualified Lambda invoke permission.
- deployment-role read preflight exercises the live provider refresh paths before Terraform plan/apply.
- Bandit, pip-audit, Checkov, Trivy, CodeQL, actionlint and a SHA-pinned zizmor engine.
- Content-Type and whitespace-only payload boundary verification before Lambda.
- deterministic live throttling verification checks effective API Gateway method settings and usage-plan/key associations instead of depending on a timing-sensitive synthetic `429` response.
- post-deployment zero-drift detection.
- production promotion requires a successful **push-triggered staging deployment for the exact Git SHA** before the production environment/OIDC job is eligible to start.
- production captures the previous immutable release version before apply and automatically restores the `prod-release` alias if a deployment fails after apply starts; the restored numeric version and `APP_VERSION` are verified.
- focused threat model in `docs/THREAT_MODEL.md`.

## Rollback model

The normal rollback path remains GitOps-controlled: identify/revert to the last known-good source/configuration through normal review, run the credential-free gates, review a fresh saved Terraform plan, apply exactly that plan, and require the live release/user-path verification plus zero drift.

Production also has a narrowly scoped **emergency release-alias rollback** inside the deployment workflow. Before Terraform apply, the workflow records the existing `prod-release` numeric Lambda version and its immutable `APP_VERSION`. If apply starts and the deployment later fails, the workflow restores that prior alias target and verifies both the numeric version and Git identity. This minimizes the duration of a bad Lambda release, but it is not claimed to be zero-risk/two-phase deployment: Terraform may already have changed other resources, and the emergency alias restoration intentionally creates desired-state drift. The failed source/configuration must then be reverted or corrected and the normal reviewed Terraform flow rerun before another promotion.

## Live evidence status

A complete staging deployment has passed the user path and live control checks on `main`. The proven staging evidence includes:

- GitHub OIDC assumption of the environment deployment role and expected AWS account;
- deployment-role live read preflight before Terraform plan/apply;
- saved-plan guard followed by application of exactly the reviewed plan;
- API-key-protected GET `/health` returning the immutable deployed Git identity;
- valid POST `/health` returning the required success response and persisting a correlated DynamoDB item;
- missing/wrong API key returning `403`;
- invalid/missing/whitespace payloads returning `400`, including boundary proof that selected invalid requests are rejected by API Gateway before Lambda;
- DynamoDB SSE with the expected customer-managed KMS key, PITR/TTL, and KMS rotation;
- Lambda placement in exactly two private subnets with no NAT/IGW;
- exactly one Lambda SG egress rule: TCP/443 to the regional DynamoDB managed prefix list, with no CIDR/IPv6/SG destination;
- exact live API Gateway GET/POST stage throttling, detailed metrics, usage-plan throttling, API/stage association and generated API-key association;
- immutable release alias bound to a numeric Lambda version whose `APP_VERSION` equals the deployed Git SHA, with exact GET/POST API Gateway invoke policy;
- post-deployment Terraform zero drift.

Production intentionally remains **not deployed** merely to demonstrate the homework. Its source path is manual-only, requires exact-SHA successful staging evidence before the prod environment job, and is designed to be combined with a GitHub `prod` Environment required-reviewer rule.
