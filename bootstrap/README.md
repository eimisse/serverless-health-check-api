# AWS bootstrap

This standalone Terraform root is the one-time trust and state bootstrap. It intentionally uses locally authenticated AWS credentials because GitHub cannot assume a deployment role until that role exists. It creates no application resources and does not store credentials in the repository.

It creates or reuses the account-wide GitHub Actions OIDC provider, a versioned/private S3 state bucket encrypted by a rotating customer-managed KMS key, separate staging/prod deployment roles, and the single regional API Gateway CloudWatch role/account setting required by both stacks.

## GitHub OIDC trust

This repository was created after GitHub's 2026-07-15 immutable OIDC-subject rollout. The trust therefore uses the repository's stable owner/repository IDs in addition to readable names:

```text
owner:      eimisse@58630165
repository: serverless-health-check-api@1349307973
```

The environment subjects are:

```text
repo:eimisse@58630165/serverless-health-check-api@1349307973:environment:staging
repo:eimisse@58630165/serverless-health-check-api@1349307973:environment:prod
```

Each deployment trust policy also independently requires:

- audience `sts.amazonaws.com`;
- repository ID `1349307973`;
- repository owner ID `58630165`;
- the matching `staging` or `prod` GitHub Environment;
- ref `refs/heads/main`.

The deployment workflow also has a `github.ref == 'refs/heads/main'` job guard. Configure the GitHub `staging` and `prod` Environments to allow deployments from `main` only as a second independent control.

These immutable identifiers prevent a later repository rename, transfer, or namespace reuse from silently inheriting AWS deployment trust.

## Remote Terraform state

The deployment roles can access only their own `env/<environment>/terraform.tfstate` object and `.tflock` object. Native S3 locking is used; no DynamoDB lock table is created.

The state bucket is:

- private with all S3 public-access controls enabled;
- versioned;
- encrypted with a rotating customer-managed KMS key;
- protected by bucket-policy denies for insecure transport, TLS below 1.2, non-KMS object encryption, and the wrong KMS key;
- protected from accidental Terraform destruction with `prevent_destroy`.

No static GitHub certificate thumbprint is pinned. The AWS provider/API handles the GitHub OIDC provider trust material, avoiding a stale thumbprint constant in this repository.

## API Gateway regional logging role

API Gateway exposes one CloudWatch role setting per AWS account and Region. Bootstrap therefore owns a single shared role and configures the regional `cloudWatchRoleArn` once rather than letting staging and prod states compete for the same singleton setting.

AWS validates this role against the service-role permissions required for API Gateway logging. The role trust is restricted to `apigateway.amazonaws.com`, and the AWS-managed service-role policy `AmazonAPIGatewayPushToCloudWatchLogs` is attached explicitly for that integration. Application access logging still targets the two environment-specific health-check log groups; the broader service-role permission is an account-level API Gateway requirement, not a Lambda runtime permission.

## Deployment policy sizing

The staging and prod deployment roles deliberately combine two policy forms:

- small inline guardrail policies for tightly coupled API Gateway/network verification constraints;
- customer-managed policies for the larger state/runtime, application, KMS, network, and observability permission sets.

This keeps each policy independently reviewable while respecting IAM policy-size quotas. The split does not broaden the actions or resource scopes: it only changes how the same least-privilege statements are packaged and attached to the environment role.

## Run once

Confirm the intended account before any write:

```bash
aws sts get-caller-identity
terraform -chdir=bootstrap init -backend=false
terraform -chdir=bootstrap fmt -check
terraform -chdir=bootstrap validate
terraform -chdir=bootstrap plan -out=bootstrap.tfplan
terraform -chdir=bootstrap apply bootstrap.tfplan
terraform -chdir=bootstrap output -json
```

Review the saved plan before applying it. The generated local bootstrap state contains security-sensitive infrastructure metadata. Keep it encrypted, access-controlled, and backed up; `.gitignore` prevents accidental commits.

If the GitHub provider already exists in the AWS account, do not create a duplicate:

```bash
terraform -chdir=bootstrap plan -out=bootstrap.tfplan \
  -var='create_github_oidc_provider=false' \
  -var='existing_github_oidc_provider_arn=arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com'
```

If an apply stops partway through, keep the local bootstrap state. Inspect it with `terraform -chdir=bootstrap state list`, update the source, create a fresh saved plan against that same state, and review the remaining in-place/create actions before retrying. Do not delete already-owned resources simply to make the second apply look clean.

## Naming exceptions

Application stacks strictly use environment-prefixed resource names. A few bootstrap resources are deliberately shared because AWS/account architecture makes them cross-environment support infrastructure:

- the Terraform state bucket and state KMS alias use a `shared-` prefix because one encrypted backend stores separate staging/prod state keys;
- the API Gateway CloudWatch role is shared because API Gateway exposes a single account-and-region CloudWatch role setting;
- the GitHub OIDC provider identity is derived from the fixed provider URL and is account-wide.

These are support/bootstrap resources, not staging/prod application resources, and the exceptions are documented rather than hidden.

## Scope notes

- Deployment roles manage only fixed application names or AWS-generated resource families constrained by project/environment tags where the service supports tag conditions.
- The API Gateway account logging setting is owned only by bootstrap. Its role trusts only the API Gateway service and carries the AWS-required logging service-role policy; application access-log destinations remain explicit staging/prod health-check log groups.
- `../security/iam-wildcard-exceptions.json` plus its narrow supplemental catalogues record reviewed wildcard permissions. Wildcard IAM actions remain prohibited.
- The S3 bucket policy wildcard principals occur only in explicit `Deny` statements and cannot grant access.
- `prevent_destroy` protects the state bucket. Cleanup therefore requires a conscious source change, a secured state backup, emptying only this exact bucket, and a reviewed saved destroy plan.
