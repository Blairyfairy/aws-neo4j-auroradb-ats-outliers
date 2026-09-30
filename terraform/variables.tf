variable "region" {
  type    = string
  default = "us-west-2"
}
variable "project" {
  type    = string
  default = "aws-neo4j-auradb"
}
variable "app_image" {
  description = "ECR image URI for the app (built from docker/Dockerfile.app)"
  type        = string
}
variable "neo4j_uri" {
  description = "AuraDB connection URI, e.g. neo4j+s://<dbid>.databases.neo4j.io"
  type        = string
}
variable "neo4j_username" {
  type    = string
  default = "neo4j"
}
variable "neo4j_password" {
  description = "AuraDB password (shown once when the instance is created)"
  type        = string
  sensitive   = true
}
variable "neo4j_database" {
  type    = string
  default = "neo4j"
}
