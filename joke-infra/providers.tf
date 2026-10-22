provider "aws" {
  region = var.region
  default_tags {
    tags = {
      project    = var.project
      env        = var.env
      managed_by = "terraform"
    }
  }
}