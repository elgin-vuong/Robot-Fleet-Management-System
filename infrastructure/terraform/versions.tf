terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state is intentionally NOT configured here. See README.md
  # "Remote state" section for the recommended S3 + DynamoDB bootstrap
  # process. Until that bootstrap is run, this configuration uses local
  # state, which is fine for a single developer working on `dev` but is
  # not safe for a team or for staging/prod.
  #
  # backend "s3" {
  #   bucket         = "<bootstrap-created-bucket>"
  #   key            = "robot-fleet/<env>/terraform.tfstate"
  #   region         = "<region>"
  #   dynamodb_table = "<bootstrap-created-lock-table>"
  #   encrypt        = true
  # }
}
