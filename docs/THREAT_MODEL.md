# Threat Model

This threat model is intentionally scoped to the candidate homework system. It does not claim that an API key provides the same assurance as user or workload identity in a high-risk production service.

## Assets

- AWS deployment privileges.
- Lambda runtime privileges.
- API key value.
- DynamoDB request records.
- Customer-managed KMS keys.
- Terraform state.
- CloudWatch application and access logs.

## Trust boundaries

1. **Internet -> API Gateway**: untrusted HTTP input enters AWS.
2. **GitHub Actions -> AWS STS**: GitHub OIDC exchanges a signed identity token for temporary AWS credentials.
3. **Deployment role -> AWS control plane**: Terraform creates and updates only project infrastructure.
4. **API Gateway -> Lambda**: only the configured `/health` GET and POST methods invoke the function.
5. **Lambda VPC -> DynamoDB**: function traffic is limited to HTTPS toward the DynamoDB managed prefix list and Gateway VPC Endpoint.
6. **DynamoDB -> KMS**: data at rest is encrypted with an environment-specific customer-managed key.
7. **Terraform -> remote state**: state is stored in a versioned, non-public, KMS-encrypted S3 bucket with native lock files.

## Threats and controls

| Threat | Control | Verification |
| --- | --- | --- |
| Long-lived AWS credential theft | GitHub OIDC + STS; no AWS access keys in GitHub | OIDC Terraform configuration, secret scanning, workflow review |
| Repository/fork assumes AWS role | OIDC `sub` restricted to this repository and exact GitHub Environment | Bootstrap trust policy |
| Over-privileged Lambda | Dedicated runtime role; exact DynamoDB `PutItem`; scoped logs; only mandatory VPC ENI actions | Terraform native tests + IAM wildcard audit |
| Over-privileged deployment pipeline | Separate staging/prod deployment roles and explicit actions/resources | Deployment IAM policy + wildcard exception catalogue |
| API Gateway regional logging role used outside its service boundary | Role trust allows only `apigateway.amazonaws.com`; bootstrap owns the singleton account/Region setting; the AWS-required logging service-role policy is isolated from Lambda/deployment roles | Bootstrap trust/policy review + live API Gateway account verification |
| Malformed request reaches application code | API Gateway JSON Schema and request validator on POST | Terraform tests + deployed negative checks |
| Unauthorized API use | API key required for GET and POST | Deployed 403 checks for missing/wrong key |
| Request burst or accidental abuse | API Gateway stage throttling, per-key usage-plan throttling, Lambda reserved concurrency | Terraform configuration + controlled staging-only 429 probe |
| API key or auth token leaked in logs | Lambda redacts `x-api-key`, `Authorization`, `Cookie`, `Proxy-Authorization` | Unit tests + deployed CloudWatch inspection |
| Secret committed to repository | `.gitignore`, OIDC, generated API key, Trivy secret scan | Blocking security gate |
| Terraform/IaC misconfiguration | Terraform validate/test, TFLint, Checkov, Trivy config | Blocking CI |
| Vulnerable Python dependency | Minimal runtime package; `pip-audit` for development dependencies | Blocking CI |
| Unsafe Python code | Unit tests, Bandit, CodeQL | CI/code scanning |
| Mutable GitHub Action compromised | Third-party actions pinned to exact commit SHAs | actionlint + zizmor + review |
| Plaintext DynamoDB data at rest | DynamoDB SSE with customer-managed KMS key and rotation | Terraform tests + live `DescribeTable`/KMS verification |
| KMS permission reused outside table | Exact runtime principal, DynamoDB `ViaService`, account and encryption-context restrictions | KMS policy tests + IAM audit |
| Lambda general Internet egress | Two private subnets, no IGW, no NAT, SG egress only to DynamoDB prefix list | Terraform + live VPC verification |
| DynamoDB endpoint used for broader data access | Endpoint policy allows only `PutItem` to exact table from exact runtime role | Terraform + live endpoint-policy verification |
| Terraform state disclosure/corruption | S3 Block Public Access, TLS enforcement, CMK encryption, versioning, native lock file | Bootstrap configuration + scans |
| Accidental destructive Terraform apply | Saved plan, JSON plan guard, exact-plan apply, post-deploy drift check | `check_terraform_plan.py` + deployment workflow |
| Accidental production deployment | Production workflow is manual-only and uses the `prod` GitHub Environment | Workflow configuration + required reviewer setting |

## API key limitation

The API key exists because the exercise requires an API-key protected endpoint and rate controls. API Gateway API keys are primarily useful for usage identification, quotas, and throttling. They are not treated here as strong end-user authentication. A higher-risk real service would normally add an authorizer or workload/user identity mechanism.

## Logging and data assumption

The exercise requires event logging and request persistence. Credential-bearing headers are therefore redacted before the event is logged. The sample `payload` is treated as non-secret test data. A real production service would apply data classification and body minimization/redaction rules appropriate to the data type.

## Deliberate exclusions

- **No NAT Gateway**: the function only needs DynamoDB. General Internet egress would add cost and attack surface.
- **No AWS WAF**: API-key protection, strict request validation, usage-plan throttling, stage throttling, and Lambda concurrency are sufficient for this bounded homework. WAF would be reasonable for a real public production threat profile.
- **No long-lived AWS credentials in GitHub**: OIDC is the only deployment authentication path.
