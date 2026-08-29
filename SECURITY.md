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
- known credential-bearing headers, query parameters and API Gateway request-context API-key fields are redacted before the incoming event is written to CloudWatch.
- Lambda runs in private subnets with no NAT/Internet Gateway path and only DynamoDB prefix-list HTTPS egress.
- the DynamoDB VPC endpoint and Lambda IAM role both restrict persistence to `PutItem` on the application table.
- DynamoDB uses a rotating customer-managed KMS key; runtime KMS use is constrained to DynamoDB and the exact table/account context, and the Lambda runtime role does not administer KMS grants.

## CI/CD security boundaries

- staging and prod use distinct deployment roles and Terraform state keys.
- GitHub OIDC trust is limited to this repository, immutable repository/owner IDs, exact GitHub Environment subjects and `main`.
- credential-free quality/security gates execute before any deployment job can obtain AWS OIDC credentials.
- critical security scans block deployment.
- wildcard IAM actions are forbidden; unavoidable wildcard resources/principals are enumerated and machine-audited.
- deployment applies the exact saved Terraform plan after the plan guard approves it.
- production is manual-only and requires a successful push-triggered staging deployment for the exact same Git SHA before its environment/OIDC job can start.
- production is intended to be protected by GitHub Environment required reviewers; this repository does not claim that GitHub UI setting exists until it is configured.
- production captures the prior immutable release before apply and can restore the `prod-release` alias after a deployment failure. That fail-safe does not replace Terraform reconciliation for other partially applied resources.

## AWS-managed API Gateway logging policy exception

`bootstrap/api_gateway_logging.tf` attaches the AWS-managed `AmazonAPIGatewayPushToCloudWatchLogs` service-role policy to the regional API Gateway CloudWatch role. AWS documents this account-level role and policy as the supported permission set for REST API CloudWatch logging. The AWS-managed policy enumerates its CloudWatch Logs actions but uses `Resource = "*"` because API Gateway may create and discover service-managed log groups and streams.

This wildcard is intentionally isolated from the application runtime and GitHub deployment roles:

- the role trust policy allows only `apigateway.amazonaws.com` to assume it;
- no `Action = "*"` permission is introduced;
- the project-owned inline policy additionally scopes normal access-log stream writes to the explicit staging/prod health-check log groups;
- Lambda runtime and GitHub deployment policies remain subject to the repository's machine-audited wildcard exception catalogues and least-privilege checks.

The AWS-managed policy is therefore treated as an AWS service-role exception, not as a general-purpose wildcard granted to application code or CI/CD. It is kept explicit in Terraform so a reviewer can distinguish the service requirement from project-authored IAM permissions.

See [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) for the scoped threat model and control mapping, and [`security/`](security/) for reviewed IAM wildcard exceptions.

Live staging verification has completed successfully for the current proven `main` release path. Production remains intentionally undeployed for homework demonstration, and its required-reviewer protection remains an external GitHub Environment configuration item that must be confirmed before any real production use.
