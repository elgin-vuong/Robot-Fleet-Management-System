########################################
# SNS topic all alarms notify. Subscribing an email is optional (and, since
# SNS email subscriptions require manual confirmation via a link in an
# email, Terraform can create the subscription but can't auto-confirm it —
# check your inbox after the first apply if you set alarm_email).
########################################

resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-alarms"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

########################################
# ECS backend service alarms
########################################

resource "aws_cloudwatch_metric_alarm" "backend_cpu_high" {
  alarm_name          = "${var.name_prefix}-backend-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  period              = 60
  statistic           = "Average"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  threshold           = var.cpu_alarm_threshold
  alarm_description   = "Backend ECS service CPU utilization is sustained above threshold."
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.backend_service_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "backend_memory_high" {
  alarm_name          = "${var.name_prefix}-backend-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  period              = 60
  statistic           = "Average"
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  threshold           = var.memory_alarm_threshold
  alarm_description   = "Backend ECS service memory utilization is sustained above threshold."
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.backend_service_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = var.tags
}

########################################
# ALB alarms
########################################

resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "${var.name_prefix}-backend-unhealthy-hosts"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  period              = 60
  statistic           = "Average"
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  threshold           = 0
  alarm_description   = "One or more backend targets are failing ALB health checks."
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.backend_target_group_arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = var.tags
}

########################################
# RDS alarms — basic operational coverage, not a substitute for
# application-level observability (see README "Observability").
########################################

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.name_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  period              = 60
  statistic           = "Average"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  threshold           = 80
  alarm_description   = "RDS CPU utilization is sustained above 80%."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_storage_low" {
  alarm_name          = "${var.name_prefix}-rds-free-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  period              = 300
  statistic           = "Average"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  threshold           = 2147483648 # 2 GiB, in bytes
  alarm_description   = "RDS free storage space is below 2 GiB."
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  tags          = var.tags
}
