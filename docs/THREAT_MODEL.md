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
3. **GitHub deployment job -> AWS STS**: the environment-scoped job exchanges a GitHub OIDC token for temporary AWS credentials.
4. **Deployment role -> AWS control plane**: Terraform creates and updates only project infrastructure.
5. **API Gateway -> Lambda release alias**: only configured `/health` GET and POST methods may invoke the environment alias.
6. **Release alias -> published Lambda version**: API traffic resolves to a numeric immutable version, never unqualified `$LATEST`.
7. **Lambda VPC -> DynamoDB**: function traffic is limited to HTTPS toward the DynamoDB managed prefix list and Gateway VPC Endpoint.
8. **DynamoDB -> KMS**: data at rest is encrypted with an environment-specific customer-managed key.
9. **Terraform -> remote state**: state is stored in a versioned, non-public, KMS-encrypted S3 bucket with native lock files.

## Threats and controls

| Threat | Control | Verification |
| --- | --- | --- |
| Long-lived AWS credential theft | GitHub OIDC + STS; no AWS access keys in GitHub | OIDC Terraform configuration, secret scanning, workflow review |
| Security/test action can mint AWS OIDC token | CI is a reusable credential-free workflow; only the dependent environment deploy job receives `id-token: write` | workflow structure + actionlint/zizmor |
| Repository/fork assumes AWS role | immutable repository/owner identity, exact GitHub Environment and `main` ref restrictions | bootstrap trust policy |
| Over-privileged Lambda | dedicated runtime role; exact DynamoDB `PutItem`; scoped logs; only mandatory VPC ENI actions | Terraform native tests + IAM wildcard audit |
| Over-privileged deployment pipeline | separate staging/prod deployment roles and explicit actions/resources | deployment IAM policies + wildcard exception catalogue |
| Shared API Gateway regional logging role is missing or incorrectly scoped | bootstrap owns the account/Region singleton; trust is restricted to `apigateway.amazonaws.com`; the AWS-required `AmazonAPIGatewayPushToCloudWatchLogs` service-role policy is attached explicitly | bootstrap recovery invariant test + Terraform/bootstrap review |
| IAM wildcard exception used to hide `Action = "*"` | literal global action and service action wildcards are absolute scanner failures, not exception-catalogue candidates | `check_iam_wildcards.py` unit tests |
| Mutable/unversioned Lambda release | `publish=true`; environment release alias targets numeric version; API integration and permission are alias-qualified | Terraform tests, plan guard, live `GetAlias`/configuration verification |
| Manual/broad Lambda alias permission drift | live alias resource policy must contain exactly two API Gateway statements scoped to GET and POST `/health` | `verify_release_alias.py` |
| Wrong Git release served | published version carries `APP_VERSION`; live alias verifier requires it to equal deployed `GITHUB_SHA` | deployment verification |
| Direct/misrouted Lambda invocation writes data | handler binds processing to `/health` and rejects another path before persistence | Lambda unit tests |
| Malformed request reaches application code | API Gateway JSON Schema and request validator on POST | Terraform tests + deployed negative checks |
| Content-Type used to bypass validation | strict model is associated with both `application/json` and `$default` | Terraform tests + live early-rejection marker proof |
| Whitespace-only payload bypasses required-field intent | JSON Schema `.*\\S.*` pattern and duplicate Lambda `strip()` validation | plan guard, Terraform/unit tests, live 400-before-Lambda proof |
| Unauthorized API use | API key required for GET and POST | deployed 403 checks for missing/wrong key |
| Request burst or accidental abuse | API Gateway stage throttling, per-key usage-plan throttling, Lambda reserved concurrency | Terraform configuration + controlled staging-only GET 429 probe |
| API key or auth token leaked in logs | Lambda redacts sensitive headers, sensitive query parameters and REST `requestContext.identity.apiKey` | unit tests + deployed CloudWatch inspection |
| Secret committed to repository | `.gitignore`, OIDC, AWS-generated API key, Trivy secret scan | blocking security gate |
| Terraform/IaC misconfiguration | Terraform validate/test, TFLint, Checkov, Trivy config | blocking reusable CI |
| Vulnerable Python dependency | minimal runtime package; `pip-audit` for production and pinned development manifests | blocking CI |
| Unsafe Python code | unit tests, Bandit, CodeQL | CI/code scanning |
| Mutable GitHub Action compromised | external actions pinned to exact commit SHAs | actionlint + zizmor + review |
| Plaintext DynamoDB data at rest | DynamoDB SSE with customer-managed KMS key and rotation | Terraform tests + live `DescribeTable`/KMS verification |
| DynamoDB resilience control removed | saved-plan guard requires PAY_PER_REQUEST, string partition key, PITR, TTL and prod deletion protection | plan-guard tests + saved deployment plan |
| KMS permission reused outside table | exact runtime principal, DynamoDB `ViaService`, account and encryption-context restrictions | KMS policy tests + IAM audit |
| Lambda general Internet egress | two private subnets, no IGW, no NAT, SG egress only to DynamoDB prefix list | Terraform + live VPC verification |
| DynamoDB endpoint used for broader data access | endpoint policy allows only `PutItem` to exact table and requires exact runtime role ARN | Terraform + live endpoint-policy verification |
| Terraform state disclosure/corruption | S3 Block Public Access, TLS enforcement, CMK encryption, versioning, native lock file | bootstrap configuration + scans |
| Accidental destructive Terraform apply | saved plan, JSON plan guard, exact-plan apply, post-deploy drift check | `check_terraform_plan.py` + deployment workflow |
| Accidental production deployment | production workflow is manual-only and uses the `prod` GitHub Environment | workflow configuration + required reviewer setting |

## API key limitation

The API key exists because the exercise requires an API-key protected endpoint and rate controls. API Gateway API keys are primarily useful for usage identification, quotas and throttling. They are not treated here as strong end-user authentication. A higher-risk real service would normally add an authorizer or workload/user identity mechanism.

## Logging and data assumption

The exercise requires event logging and request persistence. Credential-bearing headers, common secret-bearing query parameters and API Gateway's request-context API-key value are redacted before the event is logged. Redaction operates on a deep copy and does not mutate the Lambda event used by application logic.

The sample `payload` is treated as non-secret test data. A real production service would apply data classification and body minimization/redaction rules appropriate to the data type.

## Release integrity assumption

The supported release path is Git/Terraform controlled. API Gateway points at `${environment}-release`, which points at a published numeric Lambda version. A rollback reverts reviewed Git source/configuration and redeploys through the same saved-plan pipeline rather than manually editing the alias or API integration in the AWS console.

The live verifier treats an unexpected alias statement, `$LATEST`, a version mismatch or a mismatched `APP_VERSION` as a failed deployment.

## Deliberate exclusions

- **No NAT Gateway**: the function only needs DynamoDB. General Internet egress would add cost and attack surface.
- **No AWS WAF**: API-key protection, strict request validation, usage-plan throttling, stage throttling and Lambda concurrency are sufficient for this bounded homework. WAF/Shield would be reasonable for a real public production threat profile.
- **No long-lived AWS credentials in GitHub**: OIDC is the only deployment authentication path.
- **No fake pager target**: CloudWatch alarms are implemented, but no SNS/on-call destination is invented for a homework account without a real incident platform.
