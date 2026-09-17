# Root module: wires the child modules together. Each logical AWS service
# area has its own thin root file (networking.tf, security.tf, compute.tf,
# ...) that calls the corresponding module in modules/ — see README.md
# "Terraform structure" for why IAM, ECR, and Secrets Manager are
# implemented directly at root instead of as modules.

# Used to derive a globally-unique S3 bucket name without requiring the
# caller to pick one (S3 bucket names are unique across ALL AWS accounts,
# not just this one).
resource "random_id" "bucket_suffix" {
  byte_length = 4
}
