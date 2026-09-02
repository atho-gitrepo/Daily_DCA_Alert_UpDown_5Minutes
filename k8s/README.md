# Docker Desktop Kubernetes

This manifest runs the bot in safe local defaults: `DEMO` mode, one symbol, no
Telegram, and no Groq key. It expects MongoDB to be running on the laptop at
port `27017`; it reaches it through Docker Desktop's `host.docker.internal`
hostname.

## First run

1. In Docker Desktop, enable **Settings > Kubernetes > Enable Kubernetes** and
   wait until its status is running.
2. Build the image from the project root:

   ```powershell
   docker build -t daily-signal-alert:local .
   ```

3. Start local MongoDB. This container is limited to the laptop's loopback
   address and Docker restarts it automatically whenever Docker Desktop starts:

   ```powershell
   docker volume create trading-bot-mongodb-data
   docker run -d --name trading-bot-mongodb --restart unless-stopped `
     -p 127.0.0.1:27017:27017 `
     -v trading-bot-mongodb-data:/data/db `
     mongo:7
   ```

   If MongoDB is installed directly on Windows instead, ensure it is listening
   on `127.0.0.1:27017` before continuing.

4. Deploy the bot:

   ```powershell
   kubectl apply -f k8s/trading-bot.yaml
   kubectl -n trading-bot get pods --watch
   ```

5. When the bot pod is `Running`, open a local health-check tunnel:

   ```powershell
   kubectl -n trading-bot port-forward service/trading-bot 8080:8080
   ```

   In another PowerShell window:

   ```powershell
   Invoke-RestMethod http://localhost:8080/health | ConvertTo-Json -Depth 6
   ```

## Logs and lifecycle

```powershell
kubectl -n trading-bot logs deployment/trading-bot --follow
kubectl -n trading-bot rollout restart deployment/trading-bot
kubectl delete -f k8s/trading-bot.yaml
```

The Deployment uses one replica and Kubernetes restarts it whenever the
container exits. Docker Desktop starts Kubernetes when Docker Desktop starts,
so the workload comes back after a laptop restart once Docker Desktop is set
to start at sign-in. The local MongoDB container uses Docker's
`unless-stopped` restart policy for the same behaviour.

## Optional secrets

Do not put credentials in the YAML file. After rotating the Telegram token
that appeared in the shared logs, add a new secret only if notifications or AI
are desired:

```powershell
kubectl -n trading-bot create secret generic trading-bot-secrets `
  --from-literal=TELEGRAM_BOT_TOKEN='new-token' `
  --from-literal=TELEGRAM_CHAT_ID='your-chat-id' `
  --from-literal=GROQ_API_KEY='your-groq-key'
kubectl -n trading-bot rollout restart deployment/trading-bot
```

To use authenticated MongoDB, add `MONGODB_URI` to that secret; it overrides
the local unauthenticated development URI in the ConfigMap.

If Docker Desktop reports `ErrImagePull` for `daily-signal-alert:local`, build
the image again after Kubernetes is enabled, then run the rollout restart
command above.

## Production alert-monitoring configuration

This codebase does not place exchange orders. Its production configuration is
therefore suitable for production *monitoring and Telegram alerts*, not
automated real-money execution.

After rotating any credentials that were exposed, create a local secret file
from `production-secrets.env.example`. Do not put it under version control.

```powershell
Copy-Item k8s/production-secrets.env.example k8s/production-secrets.env
# Edit k8s/production-secrets.env locally with the new credentials.
kubectl -n trading-bot create secret generic trading-bot-secrets `
  --from-env-file=k8s/production-secrets.env `
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/production.yaml
kubectl -n trading-bot rollout restart deployment/trading-bot
kubectl -n trading-bot rollout status deployment/trading-bot
```

The production overlay intentionally uses the locally verified MongoDB route,
disables AI, and uses `INFO` rather than `DEBUG` logging to avoid exposing
request URLs. It is applied only after the secret exists, so the bot does not
start in production mode with missing credentials.
