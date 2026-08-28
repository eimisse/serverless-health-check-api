environment        = "staging"
aws_region         = "eu-west-1"
vpc_cidr           = "10.10.0.0/24"
availability_zones = ["eu-west-1a", "eu-west-1b"]
private_subnet_cidrs = [
  "10.10.0.0/26",
  "10.10.0.64/26",
]

lambda_memory_size          = 128
lambda_timeout_seconds      = 5
lambda_reserved_concurrency = -1
log_retention_days          = 14
request_ttl_days            = 30
max_payload_length          = 4096

dynamodb_point_in_time_recovery_enabled = true
dynamodb_deletion_protection_enabled    = false
kms_deletion_window_days                = 7
kms_rotation_period_days                = 365

stage_throttle_rate_limit  = 5
stage_throttle_burst_limit = 10
usage_plan_rate_limit      = 2
usage_plan_burst_limit     = 4

api_latency_alarm_threshold_ms = 2000

additional_tags = {
  Workload = "candidate-homework"
}
