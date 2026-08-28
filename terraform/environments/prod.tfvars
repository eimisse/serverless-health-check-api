environment        = "prod"
aws_region         = "eu-west-1"
vpc_cidr           = "10.20.0.0/24"
availability_zones = ["eu-west-1a", "eu-west-1b"]
private_subnet_cidrs = [
  "10.20.0.0/26",
  "10.20.0.64/26",
]

lambda_memory_size          = 128
lambda_timeout_seconds      = 5
lambda_reserved_concurrency = 10
log_retention_days          = 30
request_ttl_days            = 30
max_payload_length          = 4096

dynamodb_point_in_time_recovery_enabled = true
dynamodb_deletion_protection_enabled    = true
kms_deletion_window_days                = 30
kms_rotation_period_days                = 365

stage_throttle_rate_limit  = 50
stage_throttle_burst_limit = 100
usage_plan_rate_limit      = 25
usage_plan_burst_limit     = 50

api_latency_alarm_threshold_ms = 1500

additional_tags = {
  Workload = "candidate-homework"
}
