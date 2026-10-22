variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "joke"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "app_port" {
  type    = number
  default = 8000
}

variable "db_name" {
  type    = string
  default = "jokes"
}

variable "db_username" {
  type    = string
  default = "joke"
}

variable "image_tag" {
  type    = string
  default = "v1"
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "task_cpu" {
  type    = number
  default = 256
}

variable "task_memory" {
  type    = number
  default = 512
}