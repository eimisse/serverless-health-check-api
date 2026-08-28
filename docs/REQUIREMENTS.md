# Homework Requirement Coverage

This document maps each requested capability to the implementation and the evidence intended to prove it. `Implemented` means the source/configuration exists in the repository. Live AWS claims remain `pending` until the staging deployment verification workflow succeeds.

## Core requirements

| Requirement | Implementation | Verification |
| --- | --- | --- |
| All AWS infrastructure managed with Terraform | `terraform/` application root plus one-time `bootstrap/` trust/state root | `terraform validate`, native `terraform test`, TFLint, saved-plan review |
| Staging and prod | `terraform/environments/staging.tfvars` and `prod.tfvars`; separate state keys and deployment roles | Terraform tests + environment-specific deployment workflows |
| `env-resource-name` naming | naming is derived from `var.environment` / locals for all customer-named application resources, subject only to AWS-enforced syntax | Terraform tests and saved-plan guard |
| DynamoDB request table | `${environment}-requests-db`, PAY_PER_REQUEST, UUID partition key | live POST + DynamoDB `GetItem` verification |
| DynamoDB SSE | environment-specific customer-managed KMS key | Terraform tests + live `DescribeTable` |
| API Gateway `/health` | Regional REST API with API-key protected GET/POST | live HTTP smoke tests |
| Throttling | stage method throttling + usage-plan throttling + Lambda reserved concurrency | Terraform tests + controlled staging-only 429 probe |
| Lambda | Python handler, deterministic package, explicit environment-prefixed log group | unit tests + live API path |
| Incoming event logging | structured event log with credential-bearing headers, query parameters and REST request-context API-key field redacted | unit tests + live CloudWatch evidence |
| Unique request ID | UUID v4 generated per POST | unit test + response/DynamoDB correlation |
| Save request details | conditional DynamoDB `PutItem` with timestamp, TTL, metadata, payload and app version | live DynamoDB verification |
| Required success response | exact `status=healthy` / `Request processed and saved.` JSON | unit + integration test |
| Dedicated Lambda IAM role | `runtime_iam` module | Terraform tests + wildcard policy audit |
| Least privilege runtime IAM | exact DynamoDB table `PutItem`, exact log group writes, mandatory VPC ENI lifecycle only | policy tests / reviewed wildcard exception |
| Dedicated deployment role | environment-specific OIDC roles in `bootstrap/` | trust/policy review + AWS STS identity check |
| CI/CD Terraform deployment | staging deploy on `main`; manual production workflow | workflow validation + eventual staging execution |
| Lambda dependency scanning | production dependency manifest is intentionally empty; CI audits both production and pinned development manifests | `pip-audit` security gate |
| IaC security scan before apply | Checkov + Trivy before AWS OIDC apply step | deployment workflow ordering |
| No wildcard IAM actions | repository policy rejects `Action: "*"` absolutely and rejects service-level wildcard actions | `scripts/check_iam_wildcards.py` |
| Wildcard resources only where mandatory | reviewed machine-readable exception catalogue under `security/` | `scripts/check_iam_wildcards.py` occurrence audit |
| Input validation | API Gateway JSON Schema plus duplicate Lambda validation | Terraform/unit/integration tests |
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
| Automatic Lambda packaging/versioning | Implemented | deterministic `scripts/package_lambda.py`; `publish=true`; `${environment}-release` alias targets the published numeric version; API Gateway integration and invoke permissions are alias-qualified; `GITHUB_SHA` is stored as the application release identity |
| Manual approval before prod | Implemented in workflow | `prod` GitHub Environment gate; required reviewer must be configured in GitHub settings |
| Customer-managed KMS key | Implemented | environment-specific CMK with automatic rotation |
| Lambda in its own VPC | Implemented | two private subnets in separate AZs, dedicated SG |
| Invalid POST cannot reach Lambda | Implemented | strict API Gateway request model/validator including `$default` model association; live boundary probes verify invalid Content-Type and whitespace-only payload rejection before Lambda |
| API key | Implemented | AWS-generated API Gateway key + usage plan; value is never committed |

## Additional SRE/security controls

- GitHub OIDC instead of static AWS deployment credentials.
- immutable GitHub repository/owner IDs and `main` ref restriction in the AWS OIDC trust policy.
- KMS-encrypted, versioned, private Terraform state with native S3 locking.
- no NAT Gateway or Internet Gateway in the Lambda VPC.
- DynamoDB Gateway VPC Endpoint with a narrow endpoint policy.
- CloudWatch error/throttle/5XX/p95 latency alarms and dashboard.
- deterministic Lambda package hash and published immutable numeric versions.
- environment release aliases (`staging-release` / `prod-release`) keep API Gateway off unqualified `$LATEST`.
- live deployment verification resolves the release alias, requires a numeric version, and proves that version's `APP_VERSION` equals the deployed Git SHA.
- Lambda defense-in-depth route binding rejects direct/misrouted invocations outside `/health` without persistence.
- credential redaction covers sensitive headers, query-string values and `requestContext.identity.apiKey` without mutating the source event.
- DynamoDB PAY_PER_REQUEST, string partition key, PITR, TTL and production deletion protection are saved-plan invariants.
- destructive Terraform plan guard and exact saved-plan apply.
- the plan guard also blocks release alias regression to `$LATEST`, unqualified API Gateway Lambda integration and loss of alias-qualified Lambda invoke permission.
- Bandit, Checkov, Trivy, CodeQL, actionlint and a pinned zizmor engine.
- Content-Type and whitespace-only payload boundary verification before Lambda.
- post-deployment zero-drift detection.
- focused threat model in `docs/THREAT_MODEL.md`.

## Rollback model

Rollback remains GitOps-controlled. A reviewer reverts to the last known-good source commit and reruns the normal environment deployment. The deterministic package and reverted configuration are reviewed in the saved Terraform plan, Lambda publishes an immutable version for that release state, Terraform moves the environment release alias to it, and the live verifier proves the alias points at the expected Git commit. No ad-hoc API Gateway reintegration or console mutation is part of the supported rollback path.

## Live evidence status

The repository intentionally separates **source correctness** from **deployed evidence**. Until the one-time AWS bootstrap and staging workflow complete successfully, live AWS checks remain pending. The deployment workflow is designed to prove the API behavior, DynamoDB write, KMS encryption, VPC isolation, API-key rejection, early API Gateway validation, Content-Type and whitespace-only validation resistance, throttling, immutable Lambda release-alias binding, Git-release identity and zero post-deployment Terraform drift.
