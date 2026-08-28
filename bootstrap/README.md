# AWS bootstrap

This standalone Terraform root is the one-time trust and state bootstrap. It intentionally uses local AWS credentials because GitHub cannot assume a deployment role until that role exists. It creates no application resources and does not store credentials.

It creates or reuses the account-wide GitHub Actions OIDC provider, a versioned/private S3 state bucket encrypted by a rotating customer-managed KMS key, separate staging/prod deployment roles, and the single regional API Gateway CloudWatch role/account setting required by both stacks. Each deployment role's OIDC subject is exact:

- `repo:eimisse/serverless-health-check-api:environment:staging`
- `repo:eimisse/serverless-health-check-api:environment:prod`

The audience is exactly `sts.amazonaws.com`. The roles can access only their own `env/<environment>/terraform.tfstate` object and `.tflock` object. Native S3 locking is used; no DynamoDB lock table is created.

No static GitHub certificate thumbprint is pinned. The current AWS API/provider retrieves the OIDC provider thumbprint when omitted and AWS normally validates GitHub through its trusted public CA library, avoiding drift from a stale repository constant.

## Run once

Confirm the intended account before any write:

```bash
aws sts get-caller-identity
terraform init -backend=false
terraform fmt -check
terraform validate
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform output -json backend_configuration
```

The generated local bootstrap state contains security-sensitive infrastructure metadata. Keep it encrypted, access-controlled, and backed up; `.gitignore` prevents accidental commits.

If the GitHub provider already exists, do not try to create a duplicate:

```bash
terraform plan -out=bootstrap.tfplan \
  -var='create_github_oidc_provider=false' \
  -var='existing_github_oidc_provider_arn=arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com'
```

The shared state bucket and state-key alias use a `shared-` prefix because one backend protects both environment states. The GitHub OIDC provider name is derived from its fixed URL. These are deliberate exceptions to environment-prefixed application naming.

`prevent_destroy` protects the state bucket. Cleanup therefore requires a conscious source change, an independently secured state backup, emptying only this exact bucket, and a reviewed saved destroy plan.

## Scope notes

- Deployment roles manage only the fixed application names or generated-ID resource families constrained by project/environment tags.
- The API Gateway account logging setting is an AWS account-and-region singleton. Bootstrap owns it once; environment deployment roles cannot mutate it. Its shared role writes only the explicit staging/prod health-check access-log groups.
- `../security/iam-wildcard-exceptions.json` records every literal `Resource: "*"` and `Principal: "*"` exception. ARN suffix wildcards are limited to AWS-generated IDs and are tag-constrained where AWS supports tags.
- The S3 bucket policy's wildcard principal occurs only in explicit `Deny` statements and cannot grant access. Even those Deny statements enumerate the backend's exact S3 operations instead of using a wildcard action.
