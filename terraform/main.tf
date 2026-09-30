# App on ECS Fargate; the graph database is Neo4j AuraDB (managed, hosted on AWS).
# Connection details live in Secrets Manager and are injected into the task.
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.project
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project}"
  retention_in_days = 14
}

# ---- AuraDB credentials ----
resource "aws_secretsmanager_secret" "aura" {
  name                    = "${var.project}/auradb"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "aura" {
  secret_id = aws_secretsmanager_secret.aura.id
  secret_string = jsonencode({
    uri      = var.neo4j_uri
    username = var.neo4j_username
    password = var.neo4j_password
    database = var.neo4j_database
  })
}

resource "aws_iam_role" "exec" {
  name = "${var.project}-exec"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "exec" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "read_secret" {
  name = "read-auradb-secret"
  role = aws_iam_role.exec.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = aws_secretsmanager_secret.aura.arn }]
  })
}

# ---- Networking ----
resource "aws_security_group" "alb" {
  name   = "${var.project}-alb"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Egress to AuraDB (Bolt over TLS, port 7687) goes out through the task's public IP.
resource "aws_security_group" "app" {
  name   = "${var.project}-app"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "this" {
  name               = var.project
  load_balancer_type = "application"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "app" {
  name        = "${var.project}-app"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = data.aws_vpc.default.id
  health_check {
    path = "/web/"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# ---- App task + service ----
resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project}-app"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.exec.arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = var.app_image
    essential    = true
    portMappings = [{ containerPort = 8080 }]
    secrets = [
      { name = "NEO4J_URI", valueFrom = "${aws_secretsmanager_secret.aura.arn}:uri::" },
      { name = "NEO4J_USER", valueFrom = "${aws_secretsmanager_secret.aura.arn}:username::" },
      { name = "NEO4J_PASSWORD", valueFrom = "${aws_secretsmanager_secret.aura.arn}:password::" },
      { name = "NEO4J_DATABASE", valueFrom = "${aws_secretsmanager_secret.aura.arn}:database::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options   = { awslogs-group = aws_cloudwatch_log_group.this.name, awslogs-region = var.region, awslogs-stream-prefix = "app" }
    }
  }])
  depends_on = [aws_secretsmanager_secret_version.aura]
}

resource "aws_ecs_service" "app" {
  name            = "app"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8080
  }
  depends_on = [aws_lb_listener.http]
}
