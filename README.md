# Python App on AWS ECS Fargate + RDS, with Terraform

A hands-on project to learn Terraform by building a real AWS setup: a Python API running on ECS Fargate, reading from Postgres on RDS, behind a load balancer, in a private network.

Everything is built with Terraform, and everything is removed with one command.

## What's inside

```
.
├── joke-api/      A tiny FastAPI app that returns random jokes from Postgres
├── joke-infra/    Terraform code for the full AWS setup
└── loadtest.js    A k6 script to load test the deployed app
```

| Folder        | Read this if you want to                                         |
|---------------|------------------------------------------------------------------|
| `joke-infra/` | Learn Terraform, or deploy any Python app to ECS Fargate with RDS |
| `joke-api/`   | See the app contract, run the app locally, or push the image     |

Each folder has its own README with full details.

## The idea

The infra does not care what app it runs. Any Django, Flask, or FastAPI app works if it follows three rules:

1. Listens on port `8000`.
2. Has a `/health` route that returns HTTP 200.
3. Reads database settings from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.

The joke app is just a simple way to test it.

## Architecture

```
Internet -> Load balancer (public) -> ECS Fargate tasks (private) -> RDS Postgres (private)
                                              |
                                              +-> NAT gateway -> ECR, Secrets Manager, CloudWatch
```

About 32 AWS resources in total: VPC, subnets, NAT, security groups, ECR, RDS, load balancer, ECS cluster, IAM roles, and logs.

## Quick start

You need an AWS account, the AWS CLI, Terraform 1.10+, and Docker Desktop.

1. **Create the state bucket** (one time). See step 1 in `joke-infra/README.md`.
2. **Create the ECR repo.** `terraform init`, then apply only the ECR resources.
3. **Push the app image.** Build and push from `joke-api/`.
4. **Build everything else.** `terraform apply` in `joke-infra/`.
5. **Test it.** Open `<alb_url>/joke`.
6. **Load test it** (optional). See below.
7. **Destroy it.** `terraform destroy` in `joke-infra/`.

The full steps with commands are in `joke-infra/README.md`.

## Load test

Install [k6](https://k6.io), then run:

```bash
k6 run -e URL=<alb_url>/joke loadtest.js
```

It ramps up to 20 users, then 50, then back to 0, over 4 minutes. It fails if more than 1% of requests error or if p95 latency goes over 1 second.

What I saw: about 1,000 requests a minute, ECS CPU went from almost 0% to 30%, and RDS stayed at 1 connection. The app opens a new database connection on every request, so the cost showed up as CPU, not database connections. Details are in `joke-api/README.md`.

## Cost

Very roughly $80 to $90 a month if left running, mostly the NAT gateway and load balancer. Destroy it when you are done.

## What I learned

- **Plan is like `git status`, but it also checks the real AWS.** It catches changes made by hand in the console.
- **State is Terraform's memory.** Keep it in S3, never in Git.
- **Your code is the source of truth.** Manual changes in the console get undone on the next apply.
- **`moved` blocks save you during refactors.** Without one, moving a resource into a module deletes and recreates it.
- **App code and infra ship separately.** The app pipeline deploys new images. Terraform only changes the infrastructure.
- **One `destroy` removes everything.** No more hunting for leftover resources in the console.