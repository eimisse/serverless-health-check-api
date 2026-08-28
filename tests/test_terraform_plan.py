import copy
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


def valid_plan():
    return {
        "resource_changes": [
            resource(
                "module.dynamodb.aws_dynamodb_table.requests",
                after={
                    "name": "staging-requests-db",
                    "server_side_encryption": [
                        {
                            "enabled": True,
                            "kms_key_arn": "arn:aws:kms:eu-west-1:123456789012:key/example",
                        }
                    ],
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
                    "vpc_config": [
                        {
                            "subnet_ids": ["subnet-a", "subnet-b"],
                            "security_group_ids": ["sg-example"],
                        }
                    ],
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
                        "$default": "StagingHealthCheckRequest",
                        "application/json": "StagingHealthCheckRequest",
                    },
                },
            ),
            resource(
                "module.api_gateway.aws_api_gateway_request_validator.body",
                after={"validate_request_body": True},
            ),
        ]
    }


class TerraformPlanGuardTests(unittest.TestCase):
    def test_accepts_secure_non_destructive_plan(self):
        self.assertEqual(audit(valid_plan(), "staging"), [])

    def test_accepts_kms_arn_that_is_unknown_until_apply(self):
        plan = valid_plan()
        table_change = plan["resource_changes"][0]["change"]
        table_change["after"]["server_side_encryption"][0]["kms_key_arn"] = None
        table_change["after_unknown"] = {
            "server_side_encryption": [{"kms_key_arn": True}]
        }
        self.assertEqual(audit(plan, "staging"), [])

    def test_accepts_validator_id_that_is_unknown_until_apply(self):
        plan = valid_plan()
        post_change = plan["resource_changes"][4]["change"]
        post_change["after"]["request_validator_id"] = None
        post_change["after_unknown"] = {"request_validator_id": True}
        self.assertEqual(audit(plan, "staging"), [])

    def test_rejects_dynamodb_destroy(self):
        plan = valid_plan()
        plan["resource_changes"][0]["change"]["actions"] = ["delete"]
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
        plan["resource_changes"][0]["change"]["after"]["server_side_encryption"][0][
            "enabled"
        ] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("server-side encryption" in error for error in errors))

    def test_rejects_missing_kms_key_reference(self):
        plan = valid_plan()
        plan["resource_changes"][0]["change"]["after"]["server_side_encryption"][0][
            "kms_key_arn"
        ] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("server-side encryption" in error for error in errors))

    def test_rejects_disabled_kms_rotation(self):
        plan = valid_plan()
        plan["resource_changes"][1]["change"]["after"]["enable_key_rotation"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("rotation" in error for error in errors))

    def test_rejects_lambda_without_vpc_or_concurrency(self):
        plan = valid_plan()
        lambda_after = plan["resource_changes"][2]["change"]["after"]
        lambda_after["vpc_config"] = []
        lambda_after["reserved_concurrent_executions"] = -1
        errors = audit(plan, "staging")
        self.assertTrue(any("reserved concurrency" in error for error in errors))
        self.assertTrue(any("isolated VPC" in error for error in errors))

    def test_rejects_missing_get_method(self):
        plan = valid_plan()
        plan["resource_changes"] = [
            change
            for change in plan["resource_changes"]
            if change["address"] != "module.api_gateway.aws_api_gateway_method.get"
        ]
        errors = audit(plan, "staging")
        self.assertTrue(any("critical resources missing" in error for error in errors))

    def test_rejects_get_without_api_key(self):
        plan = valid_plan()
        plan["resource_changes"][3]["change"]["after"]["api_key_required"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("GET /health" in error for error in errors))

    def test_rejects_post_without_api_key_or_request_validation(self):
        plan = valid_plan()
        plan["resource_changes"][4]["change"]["after"]["api_key_required"] = False
        plan["resource_changes"][5]["change"]["after"]["validate_request_body"] = False
        errors = audit(plan, "staging")
        self.assertTrue(any("POST /health" in error for error in errors))
        self.assertTrue(any("request-body validation" in error for error in errors))

    def test_rejects_content_type_validation_bypass(self):
        plan = valid_plan()
        plan["resource_changes"][4]["change"]["after"]["request_models"].pop(
            "$default"
        )
        errors = audit(plan, "staging")
        self.assertTrue(any("$default" in error for error in errors))

    def test_rejects_detached_request_validator(self):
        plan = valid_plan()
        plan["resource_changes"][4]["change"]["after"]["request_validator_id"] = None
        errors = audit(plan, "staging")
        self.assertTrue(any("request validator" in error for error in errors))

    def test_rejects_missing_critical_resource(self):
        plan = valid_plan()
        plan["resource_changes"] = [
            change
            for change in plan["resource_changes"]
            if change["address"] != "module.kms.aws_kms_key.dynamodb"
        ]
        errors = audit(plan, "staging")
        self.assertTrue(any("critical resources missing" in error for error in errors))

    def test_environment_specific_names_are_enforced(self):
        plan = valid_plan()
        errors = audit(copy.deepcopy(plan), "prod")
        self.assertTrue(any("DynamoDB table name" in error for error in errors))
        self.assertTrue(any("Lambda function name" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
