output "dashboard_url" {
  value = "http://${aws_lb.this.dns_name}/web/"
}
output "cluster_name" {
  value = aws_ecs_cluster.this.name
}
output "auradb_secret_arn" {
  value = aws_secretsmanager_secret.aura.arn
}
