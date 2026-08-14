terraform {
  required_version = ">= 1.9.0"

  required_providers {
    # Pinned to the version already present in the local filesystem mirror
    # configured in ~/.terraformrc. See DECISIONS.md.
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.6"
    }
  }

  # Remote state is wired up by scripts/bootstrap.sh, which writes
  # backend.hcl and runs `terraform init -backend-config=backend.hcl`.
  # Native S3 state locking (use_lockfile) replaces the legacy DynamoDB
  # lock table - see DECISIONS.md.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}
