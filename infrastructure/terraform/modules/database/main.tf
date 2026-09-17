resource "random_password" "db" {
  length  = 32
  special = true
  # RDS forbids '/', '@', '"', and ' ' in passwords.
  override_special = "!#$%^&*()-_=+[]{}<>:?"
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.data_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-subnets" })
}

resource "aws_db_parameter_group" "main" {
  name   = "${var.name_prefix}-pg16"
  family = "postgres16"

  tags = var.tags
}

resource "aws_db_instance" "main" {
  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  parameter_group_name   = aws_db_parameter_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false

  multi_az                  = var.multi_az
  backup_retention_period   = var.backup_retention_days
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-postgres-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  # Performance Insights is free for 7 days of retention on most instance
  # classes — worth leaving on even in dev for query-level visibility;
  # costs money only if you extend retention beyond 7 days.
  performance_insights_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}
