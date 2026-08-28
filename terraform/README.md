# Application Terraform stack

This root module deploys one isolated `staging` or `prod` health-check API. It intentionally does not bootstrap its own backend or GitHub OIDC role; those are one-time prerequisites managed by `../bootstrap`.

## Modules

| Module | Responsibility |
| --- | --- |
| `network` | DNS-enabled VPC, two private subnets in distinct AZs, a private route table, restricted Lambda security group, and table-scoped DynamoDB gateway endpoint |
| `kms` | Rotating customer-managed DynamoDB key and environment alias with service- and encryption-context-constrained use |
| `dynamodb` | PAY_PER_REQUEST table with CMK SSE, TTL, PITR, and optional deletion protection |
| `runtime_iam` | Pre-created least-privilege runtime role, exact DynamoDB/log access, and the mandatory VPC ENI exception guard |
| `lambda` | Python 3.14 ARM64 function, deterministic ZIP hash, reserved concurrency, explicit logs, and private VPC attachment |
| `api_gateway` | REST `POST /health`, strict request model, body validator, generated API key, stage and usage-plan throttles, and structured access logs |
| `observability` | Focused Lambda error/throttle and API 5XX/p95 latency alarms plus a compact dashboard |

No NAT gateway or Internet gateway is created. Lambda HTTPS egress is restricted to the AWS-managed regional DynamoDB prefix list, and the gateway endpoint policy allows only `PutItem` to the exact request table by the exact runtime role.

## Plan and apply

Build the deterministic artifact before any Terraform operation that evaluates the function package:

```shell
python scripts/package_lambda.py
```

Copy the reviewed backend example and replace only bootstrap output placeholders:

```shell
cp terraform/environments/staging.backend.hcl.example terraform/environments/staging.backend.hcl
terraform -chdir=terraform init -backend-config=environments/staging.backend.hcl
terraform -chdir=terraform plan -var-file=environments/staging.tfvars -var="application_version=$(git rev-parse HEAD)" -out=tfplan
terraform -chdir=terraform show -json tfplan > terraform/tfplan.json
# Run the repository plan and IAM policy guards here.
terraform -chdir=terraform apply tfplan
```

Never place credentials or the API key in a tfvars/backend file. `aws_api_gateway_api_key` asks AWS to generate the key; its value is retained only in encrypted remote state and is intentionally not an output.

## API Gateway account-setting ownership

`cloudwatchRoleArn` is one mutable API Gateway account setting per AWS account and Region, not one setting per REST API. The one-time bootstrap root owns that singleton and a `shared-health-check-api-logs-role` whose write permissions cover only the two explicit application access-log groups. Neither environment state can overwrite the regional setting, so staging and prod remain safe when they share an account and Region.

## Reviewed IAM wildcard exceptions

No policy contains a wildcard action. Exact machine-readable exceptions are in `../security/iam-wildcard-exceptions.json`:

- Lambda VPC ENI lifecycle calls require `Resource: "*"`; only six exact EC2 actions are allowed. An AWS-recommended `lambda:SourceFunctionArn` Deny stops function code from using them.
- The bootstrap-owned API Gateway log role uses `logs:DescribeLogGroups`, which has no resource-level authorization support. Stream operations remain scoped to the two exact application access-log groups.
- An attached KMS key policy must express its own key as `Resource: "*"`. Principals/actions are exact, while runtime decrypt is constrained to DynamoDB, the account, and the exact table encryption context.
- A DynamoDB gateway endpoint policy uses `Principal: "*"` with `aws:PrincipalArn` fixed to the exact runtime role, one `PutItem` action, and the exact table ARN.

The standard `/aws/lambda/...` log-group prefix, generated REST API identifiers/deployments, and the regional API Gateway account object have no environment-prefixable AWS name field.
