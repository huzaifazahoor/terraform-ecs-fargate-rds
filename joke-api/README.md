# Joke API

A tiny FastAPI app that returns a random joke from a Postgres database.

It exists for one reason: to test the Terraform setup in the `joke-infra` folder. The app is simple on purpose, so the focus stays on the infrastructure. You can swap it for any Django, Flask, or FastAPI app, as long as it follows the contract below.

## What it does

| Route     | What it returns                                   |
|-----------|---------------------------------------------------|
| `/joke`   | A random joke from the database, as JSON          |
| `/health` | `{"status": "ok"}` for the load balancer to check |

On startup, the app creates a `jokes` table if it does not exist, and adds 5 jokes if the table is empty.

## The app contract

The infra in `joke-infra` will run any app that follows these rules:

1. The app listens on port `8000`.
2. The app has a `/health` route that returns HTTP 200.
3. The app reads its database settings from these env variables:

| Variable      | Example                                    |
|---------------|--------------------------------------------|
| `DB_HOST`     | `joke-dev-db.xxxx.us-east-1.rds.amazonaws.com` |
| `DB_PORT`     | `5432`                                     |
| `DB_NAME`     | `jokes`                                    |
| `DB_USER`     | `joke`                                     |
| `DB_PASSWORD` | Comes from AWS Secrets Manager on ECS      |

Keep `/health` away from the database. If it checks the database, one short database blip makes the load balancer kill every task at the same time.

## Files

| File                 | Purpose                                         |
|----------------------|-------------------------------------------------|
| `main.py`            | The FastAPI app                                 |
| `requirements.txt`   | Python packages                                 |
| `Dockerfile`         | Builds the image that runs on ECS Fargate       |
| `docker-compose.yml` | Runs the app with Postgres on your laptop       |
| `.dockerignore`      | Keeps junk out of the image                     |

## Run it on your laptop

You need Docker Desktop.

```bash
docker compose up --build
```

Then open `http://localhost:8000/joke`.

The compose file waits for Postgres to be healthy before starting the app. Without that, the app tries to seed the table before Postgres is ready and crashes.

## Push the image to AWS ECR

Do this after `joke-infra` has created the ECR repo. Get the repo URL from `terraform output ecr_repo_url`.

Replace `<ACCOUNT_ID>` with your AWS account ID.

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 -t <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/joke-dev-api:v1 .

docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/joke-dev-api:v1
```

A few things to know:

- `--platform linux/amd64` matters if you build on an ARM Mac. Fargate runs x86 by default.
- The ECR repo is immutable, so you can never push `v1` twice. Use `v2`, `v3`, or better, the git commit ID.
- On Windows PowerShell, the login pipe can fail with `400 Bad Request`. If that happens, use this instead:

```powershell
$pw = aws ecr get-login-password --region us-east-1
docker login --username AWS --password $pw <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
Remove-Variable pw
```

## Things I learned while load testing

I ran k6 with 50 users against the app on ECS. About 1,000 requests per minute reached the load balancer.

**CPU, not the database, showed the cost.** The app opens a new database connection on every request. RDS stayed at 1 connection, because each one opens and closes so fast. But ECS CPU jumped from almost 0% to 30%, because opening a new encrypted connection every time is heavy work for a 0.25 vCPU task. A connection pool would fix this.

**The seed has a race condition.** ECS starts 2 tasks at the same time. Both see an empty table and both insert the 5 jokes, so you can end up with 10 rows. Fine for a demo. In a real app, run migrations and seeding as a separate one time job, not inside each task.

## What to improve

- Add a connection pool, like `psycopg_pool`.
- Move seeding out of app startup.
- Add a GitHub Actions workflow that builds, pushes, and deploys on every merge to main.