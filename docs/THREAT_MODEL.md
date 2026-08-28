# Threat Model

This threat model is intentionally scoped to the candidate homework system. It does not claim that an API key provides the same assurance as user or workload identity in a high-risk production service.

## Assets

- AWS deployment privileges.
- Lambda runtime privileges.
- API key value.
- Immutable Lambda release identity and alias binding.
- DynamoDB request records.
- Customer-managed KMS keys.
- Terraform state.
- CloudWatch application and access logs.

## Trust boundaries

1. **Internet -> API Gateway**: untrusted HTTP input enters AWS.
2. **GitHub credential-free CI -> deployment job**: quality/security gates execute without AWS OIDC permission; only a successful gate allows the environment deployment job to start.
3. **GitHub staging evidence -> production eligibility**: production additionally requires a successful push-triggered staging deployment for the exact same Git SHA before the protected prod environment job can start.
4. **GitHub deployment job -> AWS STS**: the environment-scoped job exchanges a GitHub OIDC token for temporary AWS credentials.
5. **Deployment role -> AWS control plane**: Terraform creates and updates project infrastructure through environment-specific deployment roles.
6. **API Gateway -> Lambda release alias**: only configured `/health` GET and POST methods may invoke the environment alias.
7. **Release alias -> published Lambda version**: API traffic resolves to a numeric immutable version, never unqualified `$LATEST`.
8. **Lambda VPC -> DynamoDB**: function traffic is limited to HTTPS toward the DynamoDB managed prefix list and Gateway VPC Endpoint.
9. **DynamoDB -> KMS**: data at rest is encrypted with an environment-specific customer-managed key; runtime KMS use is constrained to the DynamoDB service path and exact table context.
10. **Terraform -> remote state**: state is stored in a versioned, non-public, KMS-encrypted S3 bucket with native lock files.

## Threats and controls

| Threat | Control | Verification |
| --- | --- | --- |
| Long-lived AWS credential theft | GitHub OIDC + STS; no AWS access keys in GitHub | OIDC Terraform configuration, secret scanning, workflow review |
| Security/test action can mint AWS OIDC token | CI is a reusable credential-free workflow; only the dependent environment deploy job receives `id-token: write` | workflow structure + actionlint/zizmor |
| Repository/fork assumes AWS role | immutable repository/owner identity, exact GitHub Environment and `main` ref restrictions | bootstrap trust policy |
| Over-privileged Lambda | dedicated runtime role; exact DynamoDB `PutItem`; scoped logs; only mandatory VPC ENI actions | Terraform native tests + IAM wildcard audit |
| Lambda runtime administers KMS grants | runtime has no `kms:CreateGrant`; deployment role retains only the service-constrained DynamoDB grant lifecycle permission | KMS native tests + IAM wildcard audit |
| Over-privileged deployment pipeline | separate staging/prod deployment roles and explicit actions/resources | deployment IAM policies + wildcard exception catalogue |
| API Gateway generated-ID resource is managed outside its environment | create requests require reviewed environment/project tags; existing RestApi/API-key/UsagePlan operations enforce supported `ResourceTag` boundaries; tag endpoint requests are restricted to reviewed keys/values | bootstrap policy review + API Gateway tag-guardrail regression tests |
| Shared API Gateway regional logging role is missing or incorrectly scoped | bootstrap owns the account/Region singleton; trust is restricted to `apigateway.amazonaws.com`; the AWS-required `AmazonAPIGatewayPushToCloudWatchLogs` service-role policy is attached explicitly | bootstrap recovery invariant test + Terraform/bootstrap review |
| IAM wildcard exception used to hide `Action = "*"` | literal global action and service action wildcards are absolute scanner failures, not exception-catalogue candidates | `check_iam_wildcards.py` unit tests |
| Mutable/unversioned Lambda release | `publish=true`; environment release alias targets numeric version; API integration and permission are alias-qualified | Terraform tests, plan guard, live `GetAlias`/configuration verification |
| Manual/broad Lambda alias permission drift | live alias resource policy must contain exactly two API Gateway statements scoped to GET and POST `/health` | `verify_release_alias.py` |
| Wrong Git release served | published version carries `APP_VERSION`; live alias verifier requires it to equal deployed `GITHUB_SHA` | deployment verification |
| Untested commit promoted to production | prod workflow requires successful push-triggered staging deployment for exact `GITHUB_SHA` before protected prod job | workflow invariant tests + GitHub Actions run query |
| Bad Lambda release remains active after failed prod deployment | previous `prod-release` numeric version and `APP_VERSION` are captured before apply; workflow restores and verifies the old alias target after a failure once apply has started | workflow invariant tests; live path would execute only during an explicitly approved prod deployment |
| Emergency alias rollback is mistaken for full infrastructure rollback | workflow/runbook explicitly treats alias restore as traffic fail-safe only; Terraform drift/partial resources must be reconciled through reviewed source/state | workflow text + runbook procedure |
| Direct/misrouted Lambda invocation writes data | handler binds processing to `/health` and rejects another path before persistence | Lambda unit tests |
| Malformed request reaches application code | API Gateway JSON Schema and request validator on POST | Terraform tests + deployed negative checks |
| Content-Type used to bypass validation | strict model is associated with both `application/json` and `$default` | Terraform tests + live early-rejection marker proof |
| Whitespace-only payload bypasses required-field intent | JSON Schema `.*\\S.*` pattern and duplicate Lambda `strip()` validation | plan guard, Terraform/unit tests, live 400-before-Lambda proof |
| Unauthorized API use | API key required for GET and POST | deployed 403 checks for missing/wrong key |
| Request burst or accidental abuse | API Gateway stage throttling + per-key usage-plan throttling; prod also has explicit Lambda reserved concurrency | Terraform tests/plan guard + live staging control-plane verification of exact rate/burst/association values |
| Flaky rate-limit observation blocks a good release | staging release gate verifies deterministic API Gateway stage/usage-plan configuration rather than requiring one timing-sensitive synthetic `429` | `verify_staging_release.py` + verifier unit tests |
| API key or auth token leaked in logs | Lambda redacts sensitive headers, sensitive query parameters and REST `requestContext.identity.apiKey` | unit tests + deployed CloudWatch inspection |
| Secret committed to repository | `.gitignore`, OIDC, AWS-generated API key, Trivy secret scan | blocking security gate |
| Terraform/IaC misconfiguration | Terraform validate/test, TFLint, Checkov, Trivy config | blocking reusable CI |
| Vulnerable Python dependency | minimal runtime package; `pip-audit` for production and pinned development manifests | blocking CI |
| Unsafe Python code | unit tests, Bandit, CodeQL | CI/code scanning |
| Mutable GitHub Action compromised | external actions pinned to exact commit SHAs | actionlint + zizmor + review |
| Plaintext DynamoDB data at rest | DynamoDB SSE with customer-managed KMS key and rotation | Terraform tests + live `DescribeTable`/KMS verification |
| DynamoDB resilience control removed | saved-plan guard requires PAY_PER_REQUEST, string partition key, PITR, TTL and prod deletion protection | plan-guard tests + saved deployment plan |
| KMS permission reused outside table | exact runtime principal, DynamoDB `ViaService`, account and encryption-context restrictions | KMS policy tests + IAM audit |
| Lambda general Internet egress | two private subnets, no IGW, no NAT, SG egress only to DynamoDB prefix list | Terraform + live VPC/SG verification |
| DynamoDB endpoint used for broader data access | endpoint policy allows only `PutItem` to exact table and requires exact runtime role ARN | Terraform + live endpoint-policy verification |
| Terraform state disclosure/corruption | S3 Block Public Access, TLS enforcement, CMK encryption, versioning, native lock file | bootstrap configuration + scans |
| Accidental destructive Terraform apply | saved plan, JSON plan guard, exact-plan apply, post-deploy drift check | `check_terraform_plan.py` + deployment workflow |
| Accidental production deployment | production workflow is manual-only, exact-SHA staging-gated, and uses the `prod` GitHub Environment | workflow configuration/invariant tests + required-reviewer setting |

## API Gateway generated-ID ABAC limitation

API Gateway management uses AWS-generated IDs for REST APIs, API keys and usage plans. The deployment role therefore cannot know all exact resource ARNs at bootstrap time and uses tag-based boundaries for these generated-ID families.

AWS exposes `aws:ResourceTag` on the actual `RestApi`, `ApiKey` and `UsagePlan` resources, so normal read/update/delete operations are denied when the resource does not carry the matching `Environment` and `Project` ownership tags. Create requests independently require the reviewed request tags, and REST API creation is additionally constrained by the exact API name.

API Gateway's special `/tags/*` pseudo-resource is different: the supported authorization path exposes request-tag and tag-key context rather than the target resource's ownership tags. Terraform also needs that endpoint during tag-on-create authorization. The bootstrap policy therefore restricts tag keys and security-relevant values and prevents removal of the Environment/Project ownership boundary, but it does **not** claim that IAM can prove the target resource's existing environment through `/tags/*` itself.

Residual risk: in a single AWS account, a compromised environment deployment role with API Gateway tag permission could attempt to apply its own valid boundary tags to another generated-ID API Gateway resource before using the normal tag-scoped management permissions. This is documented rather than hidden. For a higher-assurance production design, staging and production should live in separate AWS accounts, normally under AWS Organizations, so the account boundary remains authoritative even when a service-specific tagging endpoint cannot expose target-resource tags.

## API key limitation

The API key exists because the exercise requires an API-key protected endpoint and rate controls. API Gateway API keys are primarily useful for usage identification, quotas and throttling. They are not treated here as strong end-user authentication. A higher-risk real service would normally add an authorizer or workload/user identity mechanism.

## Logging and data assumption

The exercise requires event logging and request persistence. Credential-bearing headers, common secret-bearing query parameters and API Gateway's request-context API-key value are redacted before the event is logged. Redaction operates on a deep copy and does not mutate the Lambda event used by application logic.

The sample `payload` is treated as non-secret test data. A real production service would apply data classification and body minimization/redaction rules appropriate to the data type.

## Release integrity and rollback assumption

The normal supported release path is Git/Terraform controlled. API Gateway points at `${environment}-release`, which points at a published numeric Lambda version. A normal rollback reverts reviewed Git source/configuration and redeploys through the same saved-plan pipeline rather than manually editing the alias or API integration in the AWS console.

The live verifier treats an unexpected alias statement, `$LATEST`, a version mismatch or a mismatched `APP_VERSION` as a failed deployment.

Production adds two fail-safes: an exact-SHA successful staging deployment must exist before the prod job, and the current immutable `prod-release` target is captured before Terraform apply. If a production deployment fails after apply starts, the workflow can restore that previous alias target and verifies its numeric version plus `APP_VERSION`.

That emergency alias restoration is deliberately **not** modeled as a complete rollback or a zero-impact/canary release mechanism. Terraform may already have updated other resources, so the deployment remains failed until the source/state are intentionally reconciled and a fresh reviewed plan returns the environment to zero drift.

## Deliberate exclusions

- **No NAT Gateway**: the function only needs DynamoDB. General Internet egress would add cost and attack surface.
- **No AWS WAF**: API-key protection, strict request validation, usage-plan throttling, stage throttling and production Lambda concurrency are sufficient for this bounded homework. WAF/Shield would be reasonable for a real public production threat profile.
- **No long-lived AWS credentials in GitHub**: OIDC is the only deployment authentication path.
- **No fake pager target**: CloudWatch alarms are implemented, but no SNS/on-call destination is invented for a homework account without a real incident platform.
- **No claimed zero-downtime production canary**: exact-SHA staging proof and automatic release-alias restoration materially reduce risk, but a true two-phase/canary promotion would require a larger release-routing design and is not falsely claimed here.
