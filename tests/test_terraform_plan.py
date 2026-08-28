import copy
import json
import unittest

from scripts.check_terraform_plan import audit


def resource(address, *, after=None, after_unknown=None, actions=None):
    return {
        "address": address,
        "change": {
            "actions": actions or ["create"],
            "after": after or {},
            "after_unknown": after_unknown or {},
        },
    }


def find_change(plan, address):
    return next(
        change for change in plan["resource_changes"] if change["address"] == address
    )


def request_schema(environment="staging"):
    return json.dumps(
        {
            "$schema": "http://json-schema.org/draft-04/schema#",
            "title": f"{environment}HealthCheckRequest",
            "type": "object",
            "additionalProperties": False,
            "required": ["payload"],
            "properties": {
                "payload": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4096,
                    "pattern": ".*\\S.*",
                }
            },
        }
    )


def alias_invoke_arn(environment="staging"):
    return (
        "arn:aws:apigateway:eu-west-1:lambda:path/2015-03-31/functions/"
        f"arn:aws:lambda:eu-west-1:123456789012:function:{environment}-health-check-function:"
        f"{environment}-release/invocations"
    )


def valid_plan():
    model_name = "stagingHealthCheckRequest"
    return {
        "resource_changes": [
            resource(
                "module.dynamodb.aws_dynamodb_table.requests",
                after={
                    "name": "staging-requests-db",
                    "billing_mode": "PAY_PER_REQUEST",
                    "hash_key": "request_id",
                    "deletion_protection_enabled": False,
                    "attribute": [{"name": "request_id", "type": "S"}],
                    "server_side_encryption": [
                        {
                            "enabled": True,
                            "kms_key_arn": "arn:aws:kms:eu-west-1:123456789012:key/example",
                        }
                    ],
                    "point_in_time_recovery": [{"enabled": True}],
                    "ttl": [{"attribute_name": "expires_at", "enabled": True}],
                },
            ),
            resource(
                "module.kms.aws_kms_key.dynamodb",
                after={"enable_key_rotation": True},
            ),
            resource(
                "module.lambda.aws_lambda_function.health",
                after={
                    "function_name": "staging-health-check-function",
                    "reserved_concurrent_executions": 2,
                    "publish": True,
                    "version": "1",
                    "vpc_config": [
                        {
                            "subnet_ids": ["subnet-a", "subnet-b"],
                            "security_group_ids": ["sg-example"],
                        }
                    ],
                },
            ),
            resource(
                "module.lambda.aws_lambda_alias.release",
                after={
                    "name": "staging-release",
                    "function_name": "staging-health-check-function",
                    "function_version": "1",
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_rest_api.health",
                after={
                    "name": "staging-health-check-api",
                    "security_policy": "TLS_1_2",
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_method.get",
                after={"http_method": "GET", "api_key_required": True},
            ),
            resource(
                "module.api_gateway.aws_api_gateway_method.post",
                after={
                    "http_method": "POST",
                    "api_key_required": True,
                    "request_validator_id": "validator-123",
                    "request_models": {
                        "$default": model_name,
                        "application/json": model_name,
                    },
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_model.request",
                after={
                    "name": model_name,
                    "content_type": "application/json",
                    "schema": request_schema(),
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_request_validator.body",
                after={"validate_request_body": True},
            ),
            resource(
                "module.api_gateway.aws_api_gateway_integration.lambda_get",
                after={"uri": alias_invoke_arn()},
            ),
            resource(
                "module.api_gateway.aws_api_gateway_integration.lambda",
                after={"uri": alias_invoke_arn()},
            ),
            resource(
                "module.api_gateway.aws_api_gateway_method_settings.get",
                after={
                    "settings": [
                        {
                            "metrics_enabled": True,
                            "throttling_rate_limit": 5,
                            "throttling_burst_limit": 10,
                        }
                    ]
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_method_settings.post",
                after={
                    "settings": [
                        {
                            "metrics_enabled": True,
                            "throttling_rate_limit": 5,
                            "throttling_burst_limit": 10,
                        }
                    ]
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_api_key.health",
                after={
                    "name": "staging-health-check-api-key",
                    "enabled": True,
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_usage_plan.health",
                after={
                    "throttle_settings": [
                        {
                            "rate_limit": 2,
                            "burst_limit": 4,
                        }
                    ]
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_usage_plan_key.health",
                after={"key_type": "API_KEY"},
            ),
            resource(
                "module.api_gateway.aws_lambda_permission.api_gateway_get",
                after={
                    "action": "lambda:InvokeFunction",
                    "function_name": "staging-health-check-function",
                    "qualifier": "staging-release",
                    "principal": "apigateway.amazonaws.com",
                    "source_arn": "arn:aws:execute-api:eu-west-1:123456789012:abc/staging-health-check-stage/GET/health",
                },
            ),
            resource(
                "module.api_gateway.aws_lambda_permission.api_gateway",
                after={
                    "action": "lambda:InvokeFunction",
                    "function_name": "staging-health-check-function",
                    "qualifier": "staging-release",
                    "principal": "apigateway.amazonaws.com",
                    "source_arn": "arn:aws:execute-api:eu-west-1:123456789012:abc/staging-health-check-stage/POST/health",
                },
            ),
        ]
    }


class TerraformPlanGuardTests(unittest.TestCase):
    def test_accepts_secure_non_destructive_plan(self):
        self.assertEqual(audit(valid_plan(), "staging"), [])

    def test_accepts_kms_arn_that_is_unknown_until_apply(self):
        plan = valid_plan()
        table_change = find_change(
            plan, "module.dynamodb.aws_dynamodb_table.requests"
        )["change"]
        table_change["after"]["server_side_encryption"][0]["kms_key_arn"] = None
        table_change["after_unknown"] = {
            "server_side_encryption": [{"kms_key_arn": True}]
        }
        self.assertEqual(audit(plan, "staging"), [])

    def test_accepts_validator_id_that_is_unknown_until_apply(self):
        plan = valid_plan()
        post_change = find_change(
            plan, "module.api_gateway.aws_api_gateway_method.post"
        )["change"]
        post_change["after"]["request_validator_id"] = None
        post_change["after_unknown"] = {"request_validator_id": True}
        self.assertEqual(audit(plan, "staging"), [])

    def test_accepts_permission_source_arn_unknown_until_apply(self):
        plan = valid_plan()
        permission = find_change(
            plan, "module.api_gateway.aws_lambda_permission.api_gateway_get"
        )["change"]
        permission["after"]["source_arn"] = None
        permission["after_unknown"] = {"source_arn": True}
        self.assertEqual(audit(plan, "staging"), [])

    def test_accepts_lambda_version_unknown_until_apply(self):
        plan = valid_plan()
        lambda_change = find_change(
            plan, "module.lambda.aws_lambda_function.health"
        )["change"]
        lambda_change["after"]["version"] = None
        lambda_change["after_unknown"] = {"version": True}
        self.assertEqual(audit(plan, "staging"), [])

    def test_accepts_alias_version_and_integration_uri_unknown_until_apply(self):
        plan = valid_plan()
        alias_change = find_change(plan, "module.lambda.aws_lambda_alias.release")[
            "change"
        ]
        alias_change["after"]["function_version"] = None
        alias_change["after_unknown"] = {"function_version": True}
        integration_change = find_change(
            plan, "module.api_gateway.aws_api_gateway_integration.lambda"
        )["change"]
        integration_change["after"]["uri"] = None
        integration_change["after_unknown"] = {"uri": True}
        self.assertEqual(audit(plan, "staging"), [])

    def test_rejects_dynamodb_destroy(self):
        plan = valid_plan()
        find_change(plan, "module.dynamodb.aws_dynamodb_table.requests")["change"][
            "actions"
        ] = ["delete"]
        errors = audit(plan, "staging")
        self.assertTrue(any("destructive action" in error for error in errors))

    def test_allows_api_gateway_deployment_replacement(self):
        plan = valid_plan()
        plan["resource_changes"].append(
            resource(
                "module.api_gateway.aws_api_gateway_deployment.health",
                after={"rest_api_id": "api-example"},
                actions=["delete", "create"],
            )
        )
        self.assertEqual(audit(plan, "staging"), [])

    def test_rejects_disabled_dynamodb_encryption(self):
        plan = valid_plan()
        find_change(plan, "module.dynamodb.aws_dynamodb_table.requests")["change"][
            "after"
        ]["server_side_encryption"][0]["enabled"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("server-side encryption" in error for error in errors))

    def test_rejects_missing_kms_key_reference(self):
        plan = valid_plan()
        find_change(plan, "module.dynamodb.aws_dynamodb_table.requests")["change"][
            "after"
        ]["server_side_encryption"][0]["kms_key_arn"] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("server-side encryption" in error for error in errors))

    def test_rejects_dynamodb_resilience_regressions(self):
        plan = valid_plan()
        table = find_change(plan, "module.dynamodb.aws_dynamodb_table.requests")[
            "change"
        ]["after"]
        table["billing_mode"] = "PROVISIONED"
        table["hash_key"] = "wrong-key"
        table["attribute"] = [{"name": "request_id", "type": "N"}]
        table["point_in_time_recovery"][0]["enabled"] = False
        table["ttl"][0]["enabled"] = False

        errors = audit(plan, "staging")
        self.assertTrue(any("PAY_PER_REQUEST" in error for error in errors))
        self.assertTrue(any("partition key" in error for error in errors))
        self.assertTrue(any("string key" in error for error in errors))
        self.assertTrue(any("point-in-time recovery" in error for error in errors))
        self.assertTrue(any("TTL" in error for error in errors))

    def test_rejects_prod_without_dynamodb_deletion_protection(self):
        errors = audit(valid_plan(), "prod")
        self.assertTrue(any("production DynamoDB deletion protection" in error for error in errors))

    def test_rejects_disabled_kms_rotation(self):
        plan = valid_plan()
        find_change(plan, "module.kms.aws_kms_key.dynamodb")["change"]["after"][
            "enable_key_rotation"
        ] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("rotation" in error for error in errors))

    def test_rejects_lambda_without_vpc_or_concurrency(self):
        plan = valid_plan()
        lambda_after = find_change(
            plan, "module.lambda.aws_lambda_function.health"
        )["change"]["after"]
        lambda_after["vpc_config"] = []
        lambda_after["reserved_concurrent_executions"] = -1
        errors = audit(plan, "staging")
        self.assertTrue(any("reserved concurrency" in error for error in errors))
        self.assertTrue(any("isolated VPC" in error for error in errors))

    def test_rejects_lambda_without_immutable_version_publishing(self):
        plan = valid_plan()
        lambda_change = find_change(
            plan, "module.lambda.aws_lambda_function.health"
        )["change"]
        lambda_change["after"]["publish"] = False
        lambda_change["after"]["version"] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("version publishing" in error for error in errors))
        self.assertTrue(any("published version" in error for error in errors))

    def test_rejects_release_alias_pointing_to_latest(self):
        plan = valid_plan()
        alias_after = find_change(plan, "module.lambda.aws_lambda_alias.release")[
            "change"
        ]["after"]
        alias_after["function_version"] = "$LATEST"
        errors = audit(plan, "staging")
        self.assertTrue(any("never target $LATEST" in error for error in errors))

    def test_rejects_unqualified_api_gateway_integration(self):
        plan = valid_plan()
        integration = find_change(
            plan, "module.api_gateway.aws_api_gateway_integration.lambda"
        )["change"]["after"]
        integration["uri"] = (
            "arn:aws:apigateway:eu-west-1:lambda:path/2015-03-31/functions/"
            "arn:aws:lambda:eu-west-1:123456789012:function:staging-health-check-function/invocations"
        )
        errors = audit(plan, "staging")
        self.assertTrue(any("immutable release alias" in error for error in errors))

    def test_rejects_missing_critical_api_resource(self):
        plan = valid_plan()
        plan["resource_changes"] = [
            change
            for change in plan["resource_changes"]
            if change["address"] != "module.api_gateway.aws_api_gateway_usage_plan.health"
        ]
        errors = audit(plan, "staging")
        self.assertTrue(any("critical resources missing" in error for error in errors))

    def test_rejects_get_without_api_key(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_method.get")["change"][
            "after"
        ]["api_key_required"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("GET /health" in error for error in errors))

    def test_rejects_post_without_api_key_or_request_validation(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_method.post")["change"][
            "after"
        ]["api_key_required"] = False
        find_change(
            plan, "module.api_gateway.aws_api_gateway_request_validator.body"
        )["change"]["after"]["validate_request_body"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("POST /health" in error for error in errors))
        self.assertTrue(any("request-body validation" in error for error in errors))

    def test_rejects_content_type_validation_bypass(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_method.post")["change"][
            "after"
        ]["request_models"].pop("$default")
        errors = audit(plan, "staging")
        self.assertTrue(any("$default" in error for error in errors))

    def test_rejects_wrong_request_model_name(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_model.request")["change"][
            "after"
        ]["name"] = "WrongModel"
        errors = audit(plan, "staging")
        self.assertTrue(any("request model name" in error for error in errors))

    def test_rejects_weakened_request_schema(self):
        plan = valid_plan()
        model_after = find_change(
            plan, "module.api_gateway.aws_api_gateway_model.request"
        )["change"]["after"]
        schema = json.loads(model_after["schema"])
        schema["additionalProperties"] = True
        schema["required"] = []
        schema["properties"]["payload"]["pattern"] = ".*"
        model_after["schema"] = json.dumps(schema)
        errors = audit(plan, "staging")
        self.assertTrue(any("additional properties" in error for error in errors))
        self.assertTrue(any("require only payload" in error for error in errors))
        self.assertTrue(any("whitespace-only rejection pattern" in error for error in errors))

    def test_rejects_detached_request_validator(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_method.post")["change"][
            "after"
        ]["request_validator_id"] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("request validator" in error for error in errors))

    def test_rejects_disabled_generated_api_key(self):
        plan = valid_plan()
        find_change(plan, "module.api_gateway.aws_api_gateway_api_key.health")[
            "change"
        ]["after"]["enabled"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("API key must remain enabled" in error for error in errors))

    def test_rejects_removed_stage_throttling_or_metrics(self):
        plan = valid_plan()
        settings = find_change(
            plan, "module.api_gateway.aws_api_gateway_method_settings.post"
        )["change"]["after"]["settings"][0]
        settings["throttling_rate_limit"] = 0
        settings["metrics_enabled"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("stage rate throttling" in error for error in errors))
        self.assertTrue(any("detailed API metrics" in error for error in errors))

    def test_rejects_removed_usage_plan_throttling(self):
        plan = valid_plan()
        throttle = find_change(
            plan, "module.api_gateway.aws_api_gateway_usage_plan.health"
        )["change"]["after"]["throttle_settings"][0]
        throttle["rate_limit"] = 0
        throttle["burst_limit"] = 0
        errors = audit(plan, "staging")
        self.assertTrue(any("per-key rate throttling" in error for error in errors))
        self.assertTrue(any("per-key burst throttling" in error for error in errors))

    def test_rejects_unscoped_or_wrong_lambda_permission(self):
        plan = valid_plan()
        permission = find_change(
            plan, "module.api_gateway.aws_lambda_permission.api_gateway"
        )["change"]["after"]
        permission["principal"] = "*"
        permission["source_arn"] = None
        permission["qualifier"] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("trust only API Gateway" in error for error in errors))
        self.assertTrue(any("scoped source ARN" in error for error in errors))
        self.assertTrue(any("release-alias qualified" in error for error in errors))

    def test_rejects_lambda_permission_with_broad_method_or_path(self):
        plan = valid_plan()
        permission = find_change(
            plan, "module.api_gateway.aws_lambda_permission.api_gateway"
        )["change"]["after"]
        permission["source_arn"] = (
            "arn:aws:execute-api:eu-west-1:123456789012:abc/"
            "staging-health-check-stage/*/*"
        )
        errors = audit(plan, "staging")
        self.assertTrue(
            any("exact stage, method, and path" in error for error in errors)
        )

    def test_environment_specific_names_are_enforced(self):
        plan = valid_plan()
        errors = audit(copy.deepcopy(plan), "prod")
        self.assertTrue(any("DynamoDB table name" in error for error in errors))
        self.assertTrue(any("Lambda function name" in error for error in errors))
        self.assertTrue(any("release alias name" in error for error in errors))
        self.assertTrue(any("API Gateway name" in error for error in errors))
        self.assertTrue(any("request model name" in error for error in errors))
        self.assertTrue(any("API key name" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
