output "ecr_repo_url" {
  value = aws_ecr_repository.app.repository_url
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "db_secret_arn" {
  value = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "alb_url" {
  value = "http://${aws_lb.main.dns_name}"
}