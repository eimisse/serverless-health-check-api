# Security Policy

## Reporting a security issue

Do not open a public issue for credentials, private keys, API-key values, Terraform state, or another suspected secret exposure. Report the finding privately to the repository owner and rotate/revoke the affected credential before publishing details.

## Repository security rules

Never commit:

- AWS access keys or session credentials;
- API-key values;
- private keys or certificates containing private material;
- Terraform state or saved Terraform plans;
- generated Lambda ZIP packages;
- local `.env` or AWS credential files.

GitHub deployment authentication uses short-lived OIDC credentials. Long-lived `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` GitHub secrets are intentionally not part of this design.

## Runtime security boundaries

- API Gateway requires an API key for both exposed `/health` methods.
- `POST /health` uses a strict request model and `$default` model association so changing `Content-Type` cannot bypass the API Gateway body validator.
- Lambda repeats input validation as defense in depth.
- known credential-bearing headers are redacted before the incoming event is written to CloudWatch.
- Lambda runs in private subnets with no NAT/Internet Gateway path and only DynamoDB prefix-list HTTPS egress.
- the DynamoDB VPC endpoint and Lambda IAM role both restrict persistence to `PutItem` on the application table.
- DynamoDB uses a rotating customer-managed KMS key.

## CI/CD security boundaries

- staging and prod use distinct deployment roles and Terraform state keys.
- GitHub OIDC trust is limited to this repository and exact GitHub Environment subjects.
- critical security scans block deployment.
- wildcard IAM actions are forbidden; unavoidable wildcard resources/principals are enumerated and machine-audited.
- deployment applies the exact saved Terraform plan after the plan guard approves it.
- production deployment is manual-only and is intended to be protected by GitHub Environment required reviewers.

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for the scoped threat model and control mapping, and [`security/`](security/) for reviewed IAM wildcard exceptions.

Until bootstrap, GitHub Environment protection, and live staging verification are completed, the repository does not claim that an AWS environment is deployed or that production approval rules are active.
