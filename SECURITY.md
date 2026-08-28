# Security Policy

Do not commit credentials, API keys, private keys, Terraform state, saved plans,
or generated deployment packages. Report a suspected exposure privately to the
repository owner and rotate the affected credential before publishing details.

The final deployment uses short-lived GitHub OIDC credentials. Until bootstrap
and CI are configured, this repository makes no claim that an AWS environment is
deployed or that GitHub Environment approval rules are active.
