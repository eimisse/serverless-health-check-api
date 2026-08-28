output "dashboard_name" {
  description = "Focused CloudWatch dashboard name."
  value       = aws_cloudwatch_dashboard.service.dashboard_name
}

output "alarm_names" {
  description = "CloudWatch service alarm names."
  value = [
    aws_cloudwatch_metric_alarm.lambda_errors.alarm_name,
    aws_cloudwatch_metric_alarm.lambda_throttles.alarm_name,
    aws_cloudwatch_metric_alarm.api_5xx.alarm_name,
    aws_cloudwatch_metric_alarm.api_latency.alarm_name,
  ]
}
