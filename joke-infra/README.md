# Joke Infra

Terraform code that runs any Python web app on AWS ECS Fargate with a Postgres database on RDS.

The `joke-api` folder has a small FastAPI app to test it with. But this infra does not care what the app is. Any Django, Flask, or FastAPI app works, as long as it follows the app contract (see the `joke-api` README).

This README has two parts:

1. **Learn Terraform**: the ideas you need, in plain words.
2. **Deploy it**: step by step, from zero to a working URL, and back to zero.

---

## What it builds

```
                 Internet
                    |
          +---------v----------+
          |   Load balancer    |   public subnets
          |   (port 80)        |
          +---------+----------+
                    |
        +-----------v-----------+
        |  ECS Fargate tasks    |   private subnets
        |  (your app, x2)       |
        +-----+-----------+-----+
              |           |
     +--------v---+   +---v--------------+
     |  RDS       |   |  NAT gateway     |---> Internet (pull image,
     |  Postgres  |   |  (one way out)   |     read secrets, logs)
     +------------+   +------------------+
```

In total, about 32 AWS resources:

| Part           | What it is                                                         |
|----------------|--------------------------------------------------------------------|
| Network        | VPC, 2 public subnets, 2 private subnets, internet gateway, NAT, route tables |
| Security       | 3 security groups that only let the right traffic in               |
| ECR            | Image repo for your app, keeps the last 10 images                  |
| RDS            | Postgres 16, private, password kept by AWS in Secrets Manager      |
| Load balancer  | Public entry point, checks `/health` on each task                  |
| ECS            | Cluster, IAM roles, log group, task definition, service with 2 tasks |

---

# Part 1: Learn Terraform

## What Terraform is

Terraform lets you describe your cloud setup in files, then builds it for you.

You write what you want, like "one VPC, two subnets, one database." Terraform compares that to what exists, and only makes the changes needed. This idea is called **desired state**. Kubernetes works the same way.

Terraform works with AWS, Azure, GCP, and many more. But the code is still different for each one, because each cloud has different services. You learn one tool and one language, not one set of code for every cloud.

Terraform is made by HashiCorp, now owned by IBM. After a license change in 2023, the community made a free fork called **OpenTofu**. It works almost the same.

## Where the code runs

Terraform does not run inside AWS. It runs wherever you run the `terraform` command, your laptop or a CI pipeline like GitHub Actions. From there, it calls AWS APIs to create things.

When GitHub Actions runs it, the machine is thrown away after the run. But the things it created stay in AWS.

## The main loop

| Command             | What it does                                              | Like in Git        |
|---------------------|-----------------------------------------------------------|--------------------|
| `terraform init`    | Downloads providers and sets up the backend               | `git clone`        |
| `terraform plan`    | Shows what will change. Changes nothing.                  | `git status`       |
| `terraform apply`   | Makes the changes for real                                | `git commit`       |
| `terraform destroy` | Deletes everything Terraform created                      | no match           |

One difference from `git status`: plan also checks the real AWS, so it catches changes someone made by hand.

## Reading a plan

| Symbol | Meaning                          | Watch out                         |
|--------|----------------------------------|-----------------------------------|
| `+`    | Create                           |                                   |
| `~`    | Update in place                  |                                   |
| `-/+`  | Delete, then create again        | On a database, this means data loss |
| `-`    | Destroy                          |                                   |

Always read the last line, like `Plan: 3 to add, 0 to change, 0 to destroy`. In a PR review, any surprise destroy is a red flag.

## The parts of a Terraform file

```hcl
terraform {                         # 1. Which providers and where state lives
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {                    # 2. How to talk to AWS
  region = "us-east-1"
}

resource "aws_s3_bucket" "learning" {   # 3. A thing to build
  bucket = "my-bucket-name"
}
```

- A **provider** is the plugin that turns your code into AWS API calls.
- A **resource** is one real thing in the cloud. `aws_s3_bucket` is the type. `learning` is Terraform's own name for it, used only inside your code.
- To use a value from another resource, write `type.name.attribute`, like `aws_s3_bucket.learning.arn`. Terraform also uses these links to know what to build first.

Terraform reads every `.tf` file in a folder as one big file. Splitting into `network.tf`, `rds.tf`, and so on is only for humans.

## State: how Terraform remembers

After an apply, Terraform writes a **state file**. It links each name in your code to the real thing in AWS. For example, `aws_s3_bucket.learning` points to the real bucket ID.

That is how Terraform knows next time that the bucket already exists, and does not create a second one.

Rules for state:

- **Never commit it to Git.** It can hold secrets in plain text.
- **Never edit it by hand.**
- **Store it remotely**, like in S3. On a laptop, only you can see it. In GitHub Actions, it would vanish with the machine.

This repo stores state in S3:

```hcl
backend "s3" {
  bucket       = "your-state-bucket"
  key          = "joke/dev/terraform.tfstate"
  region       = "us-east-1"
  use_lockfile = true
}
```

`use_lockfile = true` makes a small lock file during each run, so two runs cannot change things at the same time. You will see `Releasing state lock` at the end of every command.

The backend block cannot use variables. That is a known Terraform limit.

## Drift: when someone changes things by hand

If someone changes a resource in the AWS console, the real thing no longer matches your code. This is called **drift**. The next `plan` shows it, and the next `apply` puts it back to match your code.

Your code is the source of truth, not the console. That is why teams ban manual changes. The next apply quietly undoes them.

If you want to keep a manual change, you have three options:

| Situation                                   | Fix                                    |
|---------------------------------------------|----------------------------------------|
| You like the manual change                  | Update your code to match it           |
| Someone made a whole resource by hand       | Bring it in with an `import` block     |
| A field is meant to change outside Terraform | `lifecycle { ignore_changes = [...] }` |

## Variables and outputs

Think of them as function inputs and return values.

```hcl
# variables.tf
variable "env" {
  type    = string
  default = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be dev, staging, or prod."
  }
}
```

Use it as `var.env`. Always set `type`, so a wrong value fails at plan time with a clear error. Terraform has no enum type, so use a `validation` block.

Ways to give a variable a value, from simplest to best for CI:

1. A `default` in the variable block.
2. A `terraform.tfvars` file. Terraform loads it by itself.
3. An env variable named `TF_VAR_<name>`, like `TF_VAR_env=prod`.

For secrets in GitHub Actions, map a GitHub secret to a `TF_VAR_` env variable. Mark the variable `sensitive = true` so it is hidden in plan output. It still sits in the state file, so lock down your state bucket.

```hcl
# outputs.tf
output "alb_url" {
  value = "http://${aws_lb.main.dns_name}"
}
```

Outputs print after apply, and you can read them anytime with `terraform output`. Inside the same code you do not need outputs, you can link resources directly. Outputs are for crossing a boundary: from a module back to the main code, from Terraform to GitHub Actions, or to a human.

## Modules

A module is a folder of `.tf` files with its own variables and outputs. It is like a function you can call many times.

```hcl
module "dev" {
  source      = "./modules/s3_bucket"
  bucket_name = "my-dev-bucket"
  env         = "dev"
}
```

Read its outputs as `module.dev.bucket_arn`. A module should never set its own region or backend. The caller decides that.

When you move a resource into a module, its address changes. Without help, Terraform deletes the old one and creates a new one. A `moved` block tells Terraform it is the same thing:

```hcl
moved {
  from = aws_s3_bucket.learning
  to   = module.dev.aws_s3_bucket.learning
}
```

## Other things used in this repo

| Feature          | What it does                                                         |
|------------------|----------------------------------------------------------------------|
| `count = 2`      | Makes 2 copies of a resource, like one subnet per zone               |
| `[*]`            | Gets a field from all copies, like `aws_subnet.private[*].id`        |
| `data` source    | Reads something that already exists, like which zones are available  |
| `locals`         | Named values you reuse, like `local.name = "joke-dev"`               |
| `default_tags`   | Adds tags like `project` and `managed_by` to every resource          |
| `jsonencode()`   | Writes JSON, like IAM policies and container settings, in Terraform  |

---

# Part 2: Deploy it

## What you need

- An AWS account and the AWS CLI logged in. Check with `aws sts get-caller-identity`.
- Terraform 1.10 or newer. Check with `terraform -version`.
- Docker Desktop, to build and push the app image.

Watch your CLI region. If your default is not `us-east-1`, add `--region us-east-1` to AWS commands, or you will think your resources disappeared.

## Files

| File            | What it builds                                             |
|-----------------|------------------------------------------------------------|
| `versions.tf`   | Terraform and provider versions, S3 backend                |
| `providers.tf`  | AWS provider and default tags                              |
| `variables.tf`  | All inputs                                                 |
| `network.tf`    | VPC, subnets, internet gateway, NAT, route tables          |
| `security.tf`   | Security groups for the load balancer, ECS, and RDS        |
| `ecr.tf`        | Image repo and cleanup rule                                |
| `rds.tf`        | Postgres database and its subnet group                     |
| `alb.tf`        | Load balancer, target group, listener                      |
| `ecs.tf`        | Cluster, IAM roles, log group, task definition, service    |
| `outputs.tf`    | URLs and IDs you need after apply                          |

## Variables

| Name            | Default     | What it controls                    |
|-----------------|-------------|-------------------------------------|
| `region`        | `us-east-1` | AWS region                          |
| `project`       | `joke`      | Used in every resource name         |
| `env`           | `dev`       | Used in every resource name         |
| `app_port`      | `8000`      | Port your app listens on            |
| `db_name`       | `jokes`     | Database name                       |
| `db_username`   | `joke`      | Database user                       |
| `image_tag`     | `v1`        | Which image tag ECS runs            |
| `desired_count` | `2`         | How many tasks run                  |
| `task_cpu`      | `256`       | CPU per task (256 = 0.25 vCPU)      |
| `task_memory`   | `512`       | Memory per task in MB               |

## Step 1: Create the state bucket (one time only)

Terraform cannot store state in a bucket that does not exist yet. So you make this one bucket by hand. Bucket names are global, so pick a unique one, and put it in `versions.tf`.

```bash
aws s3api create-bucket --bucket your-tf-state-bucket --region us-east-1
aws s3api put-bucket-versioning --bucket your-tf-state-bucket --versioning-configuration Status=Enabled
```

Versioning keeps every old copy of your state, so you can roll back if a bad apply breaks it.

## Step 2: Init

```bash
cd joke-infra
terraform init
```

## Step 3: Create the ECR repo first

ECS needs an image to run. So create the ECR repo first, push the image, then build the rest.

```bash
terraform apply -target=aws_ecr_repository.app -target=aws_ecr_lifecycle_policy.app
terraform output ecr_repo_url
```

Use `-target` only for first time setup like this. In normal work, always apply everything.

## Step 4: Push the app image

Follow the "Push the image to AWS ECR" part in the `joke-api` README.

## Step 5: Build everything else

```bash
terraform plan
terraform apply
```

RDS takes about 5 minutes, the load balancer about 2, and the NAT gateway about 2.

## Step 6: Test it

```bash
terraform output alb_url
```

Wait a minute or two for tasks to start and pass health checks. Then open `<alb_url>/joke`.

If you get 502 or 503 after a few minutes, check the logs:

```bash
aws logs tail /ecs/joke-dev-api --region us-east-1 --since 10m
```

## How things connect

**Security groups use groups, not IPs.** The load balancer accepts port 80 from anyone. ECS accepts the app port only from the load balancer's group. RDS accepts 5432 only from the ECS group. This stays locked even when task IPs change.

**Private subnets go out through the NAT.** ECS tasks have no public IP. They reach ECR, Secrets Manager, and CloudWatch through the NAT gateway. Nothing from outside can reach in.

**The password never appears in code or state.** RDS creates it and stores it in Secrets Manager (`manage_master_user_password = true`). ECS pulls just the password field with `<secret_arn>:password::` and gives it to the app as `DB_PASSWORD`.

**Two IAM roles, two jobs.** The execution role is what ECS uses to pull the image, read the secret, and write logs. The task role is what your app code can do in AWS. It is empty here, add permissions when your app needs S3 or SQS.

**The circuit breaker.** If new tasks keep crashing, ECS stops the deploy and rolls back by itself.

## Deploying new app versions

App code and infra change in different ways:

| Change                             | How it ships                                  |
|------------------------------------|-----------------------------------------------|
| New app code                       | App pipeline builds, pushes, and deploys to ECS |
| More CPU, new env var, new service | Terraform                                     |

The ECS service has `ignore_changes = [task_definition]`. This means the app pipeline can deploy new images without Terraform undoing them. The trade-off: if you change the task definition in Terraform, like adding an env var, the service will not pick it up until the next app deploy.

## Using your own app

1. Make sure your app follows the contract: port, `/health`, and the `DB_` env variables.
2. If your app uses a different port, set `app_port`.
3. Push your image to the ECR repo and set `image_tag` to match.
4. Need more env variables? Add them to `environment` in `ecs.tf`. Secrets go in `secrets`.

## Rough cost

With the defaults, running all month in us-east-1, expect very roughly $80 to $90 a month. The NAT gateway (about $33) and the load balancer (about $17) are the biggest parts, plus RDS, Fargate, and data transfer. Check the AWS pricing pages for current prices. Destroy it when you are done learning.

## Load test results

I ran k6 with up to 50 users from my laptop. About 1,000 requests a minute reached the load balancer. ECS CPU went from almost 0% to 30%, and RDS stayed at 1 connection. The app opens a new database connection on every request, and that costs CPU on a tiny task. See the `joke-api` README for details.

To check metrics from the command line:

```bash
aws cloudwatch get-metric-statistics --region us-east-1 \
  --namespace AWS/ECS --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=joke-dev-cluster Name=ServiceName,Value=joke-dev-api \
  --start-time <start> --end-time <end> --period 60 --statistics Average
```

## Destroy everything

```bash
terraform destroy
```

This removes all 32 resources. ECR has `force_delete = true`, so it deletes even with images inside. RDS has `skip_final_snapshot = true`, so no snapshot is left behind.

Then check nothing is left, using the tags from `default_tags`:

```bash
aws resourcegroupstaggingapi get-resources --tag-filters Key=project,Values=joke --region us-east-1
```

Deleted resources can show up here for a while after deletion. The state bucket from step 1 is not managed by Terraform, so delete it by hand if you are done for good.

## Before using this in production

This setup is built for learning. For production, change these:

- **One NAT gateway per zone.** One NAT is a single point of failure.
- **HTTPS.** Add an ACM certificate and a port 443 listener.
- **Protect the database.** Set `deletion_protection = true` and `skip_final_snapshot = false`.
- **Multi-AZ RDS**, so the database survives a zone failure.
- **Separate state per environment**, like `joke/dev/` and `joke/prod/`, so a bad apply in dev cannot touch prod.
- **Auto scaling** for the ECS service, based on CPU.
- **GitHub Actions with OIDC**, so CI uses short-lived AWS roles instead of saved access keys.
- **Run plan on every PR and apply on merge**, so every change is reviewed.