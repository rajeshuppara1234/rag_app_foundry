# Run locally, then deploy manually with Microsoft Foundry

This guide is for the current `rag_app_foundry` project on Windows. All terminal commands below use **PowerShell** and are instructions for you to run. Creating this guide does not deploy resources or change the application.

Authentication and token handling stay as currently implemented. Reuse your working endpoints, credentials, token settings and Chroma collection.

## What you will run

Start locally, verify the existing services, and then publish the same application to Azure:

```text
Local development:
Browser -> FastAPI on your PC -> Foundry models + existing Chroma server

Azure deployment:
Browser -> HTTPS -> Web Container App -> Foundry models
                                    -> Existing Chroma Container App
                                       with its existing persistent storage
```

**Where Foundry fits:** your current code uses Foundry for chat and embedding models. The website and FastAPI server run on Azure Container Apps. Foundry also supports hosted agents, but this repository's web server has not been adapted to that hosting interface. The manual steps below deploy the current application using your Foundry resources. See the final section if you specifically want a Foundry-hosted agent endpoint. [Microsoft hosting guidance](https://learn.microsoft.com/en-us/azure/container-apps/ai-integration), [Foundry hosted-agent quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-deploy-own-code).

**API:** already implemented at `POST /api/chat`. **MCP:** not required for this browser application.

## Part 1 — Run on your Windows system

### Step 1. Open the project folder

Open PowerShell or the VS Code terminal:

```powershell
Set-Location 'D:\learning\langchain\rag_app_foundry'
```

Run all project commands from this directory, so the application can find `.env` and the `app` package.

### Step 2. Check the tools

```powershell
uv --version
node --version
npm.cmd --version
az --version
```

You need:

| Tool | Purpose |
| --- | --- |
| Python 3.12 and `uv` | Install dependencies and run Python |
| Node.js and npm | Build the browser interface; Node.js 24 matches the Dockerfile |
| Azure CLI | Azure login and the later cloud image build |
| Docker Desktop | Optional local container testing; not needed for the normal local run or `az acr build` |

If a tool is missing, install it from its official site: [uv](https://docs.astral.sh/uv/getting-started/installation/), [Node.js](https://nodejs.org/en/download), [Azure CLI for Windows](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows). Open a new terminal after installation.

### Step 3. Install the Python dependencies

```powershell
uv sync --frozen
```

This uses the existing lockfile and prepares `.venv`. You do not need to activate the environment when using `uv run`.

If you also want to run the older local sentence-transformer or FAISS learning examples:

```powershell
uv sync --frozen --extra learning
```

Those optional packages are not required for the Azure embedding path.

### Step 4. Check your local configuration

Keep your existing `.env`. Use [.env.example](.env.example) as a reference and fill missing settings in your local file. Only if you have no `.env` yet:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Check these settings against your existing services:

| Setting | Local value / meaning |
| --- | --- |
| `FOUNDRY_OPENAI_ENDPOINT` | Your chat resource endpoint ending in `/openai/v1/` |
| `FOUNDRY_CHAT_MODEL` | Your deployed chat model's **deployment name** |
| `AZURE_OPENAI_ENDPOINT` | Your embedding resource's base endpoint |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Deployment used to generate the existing stored embeddings |
| `AZURE_OPENAI_API_VERSION` | Keep your currently working value; the code defaults to `2024-02-01` |
| `CHROMA_URL` | Existing Chroma HTTP(S) URL reachable from your PC |
| `CHROMA_COLLECTION` | Existing collection name, usually `pdf_documents` |
| `CHROMA_TENANT` | Existing tenant; default is `default_tenant` |
| `CHROMA_DATABASE` | Existing database; default is `default_database` |
| `APP_ENV` | `development` for the local web application |
| `PUBLIC_ORIGIN` | `http://localhost:8000` for the local web application |

Endpoint examples show the required **shape**, not credentials to copy:

```dotenv
FOUNDRY_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
FOUNDRY_CHAT_MODEL=YOUR-CHAT-DEPLOYMENT
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=YOUR-EMBEDDING-DEPLOYMENT
CHROMA_URL=https://YOUR-CHROMA-HOST
CHROMA_COLLECTION=pdf_documents
APP_ENV=development
PUBLIC_ORIGIN=http://localhost:8000
```

Use the resource endpoint shown for your model deployment. A Foundry **project** URL containing `/api/projects/...` is not the chat endpoint. `FOUNDRY_PROJECT_ENDPOINT` is used by the separate project-SDK example, not by the web app's normal RAG path.

**Keep your existing model authentication method:**

- If using keys, retain `FOUNDRY_API_KEY` for chat and `AZURE_OPENAI_API_KEY` for embeddings in your local `.env`.
- If the relevant key is omitted, that client uses `DefaultAzureCredential`. For your PC, sign in with an account that has access to the model resource:

```powershell
az login
az account set --subscription '<your-subscription-id>'
```

If your Azure resources require a particular tenant, use `az login --tenant '<resource-tenant-id>'`. This is the Azure resource tenant, which may differ from the customer sign-in tenant.

Retain `CHROMA_AUTH_HEADER` and `CHROMA_AUTH_TOKEN` if your existing Chroma proxy requires them. A Chroma endpoint limited to a Container Apps environment is not normally reachable directly from your PC; use your established private-network access or run these backend checks from a trusted workload in that environment. Do not change database exposure just to make a local test work.

### Step 5. Verify the backend before starting the browser app

These commands use your existing backend credentials. They do not require browser `AUTH_*` settings.

**5a. Test the chat model:**

```powershell
uv run python foundry_llm.py
```

Expected: a short explanation of vector embeddings. This makes a real model request.

**5b. Test the embedding deployment:**

```powershell
uv run python -c "from app.ingestion.embeddings import EmbeddingManager; manager = EmbeddingManager(); vectors = manager.generate_embeddings(['Hello world']); print('Embedding dimensions:', len(vectors[0])); manager.close()"
```

Expected: a positive embedding dimension. It must match the vectors in your existing collection. This also makes a real model request.

**5c. Check the existing collection without adding documents:**

```powershell
uv run python -c "from app.retrieval.vector_store import VectorStore; store = VectorStore(); print('Stored chunks:', store.collection.count())"
```

Expected: the stored chunk count. If the collection is missing, this command fails rather than creating a replacement.

**5d. Run the complete RAG pipeline from the terminal:**

```powershell
uv run python -m app.retrieval.augument_gen
```

This runs the current example question, **“What is LangChain?”**, retrieves from Chroma and prints the generated answer. An “I don't know” response can be correct if the documents do not cover that question. A successful grounded answer confirms the basic embedding → retrieval → generation path.

**If you want to postpone browser authentication setup, you can stop here and use this terminal example for now.** This does not disable or bypass web API authentication.

### Step 6. Ingest documents only if needed

Skip this step if the intended documents are already indexed.

To add the PDFs in `app/data` to an existing collection:

```powershell
uv run python -m app.retrieval.vector_store --data-dir app/data
```

Only when you intentionally want to create a new collection:

```powershell
uv run python -m app.retrieval.vector_store --data-dir app/data --create-collection
```

These commands write to Chroma. Keep the existing embedding deployment when querying an existing collection. Previously indexed UUID-based chunks are not automatically deduplicated by the newer ingestion code, so do not reingest an existing corpus simply to start the app. Changing embedding models or dimensions requires a separately rebuilt collection.

### Step 7. Build the browser interface

```powershell
npm.cmd --prefix web ci
npm.cmd --prefix web run build
```

Expected: `app/static/index.html` and files under `app/static/assets` are generated. FastAPI serves them; you do not need a second frontend server.

### Step 8. Preserve and check the existing browser authentication settings

The current web application requires these configured settings:

```text
AUTH_AUTHORITY
AUTH_ISSUER
AUTH_JWKS_URL
AUTH_AUDIENCE
AUTH_SPA_CLIENT_ID
AUTH_SCOPE
AUTH_REQUIRED_SCOPE   (defaults to access_as_user)
```

Reuse the existing values. The SPA's configured redirect URI must include `http://localhost:8000/`. `PUBLIC_ORIGIN` is the same origin **without** the trailing slash.

There are two separate authentications: `az login` or a model API key lets the backend call Foundry; the browser's user access token lets a signed-in user call `/api/chat`. They are not interchangeable.

If the `AUTH_*` values have not yet been configured, the web app will fail startup. Placeholder values do not provide working sign-in. Continue with Step 5's terminal example until those existing settings are available. This guide does not change the authentication implementation or add a development bypass.

### Step 9. Start the web application

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Keep this terminal open. Open **http://localhost:8000/** in your browser, sign in through the existing flow, and ask a question covered by the indexed documents.

Use `localhost` consistently; switching the browser to `127.0.0.1` changes the origin and can conflict with your existing redirect configuration. The server can bind to `127.0.0.1` while the browser uses `localhost`.

In a second PowerShell terminal, check:

```powershell
Invoke-RestMethod 'http://localhost:8000/health/live'
Invoke-RestMethod 'http://localhost:8000/health/ready'
```

Expected: `status: ok` and `status: ready`. Readiness checks that the Chroma collection exists and is nonempty; it does not test model permissions. Test an actual signed-in question as well.

Stop the local server with **Ctrl+C**. Start it again later with the same `uv run uvicorn ...` command. Rebuild frontend files only after frontend changes. `/docs` is disabled in the current application.

## Part 2 — Deploy the current app manually to Azure

The following steps use the Azure portal plus an explicit image-build command. They do not require GitHub Actions or running the Bicep template.

### Step 10. Record your existing Azure resource details

Open your Foundry project and its model-deployment details, then the Azure portal. Record:

| Detail | Where it is used |
| --- | --- |
| Subscription ID and resource group | Select the deployment destination |
| Existing chat/embedding resource endpoints and deployment names | Same configuration verified locally |
| Existing Chroma Container App and collection name | Keep using the persistent database |
| Chroma's Container Apps environment and region | Place the new web app in that environment |
| Azure Container Registry name/login server | Store and pull your application image |
| Current authentication method/settings | Reuse them in the deployed application |

Create a **separate web Container App**, for example `rag-web`. Keep the existing Chroma app, storage mount and database in place. The web app does not need to mount the Chroma data volume; it talks to the Chroma server over HTTP(S).

For a public URL, the Container Apps environment must have a public ingress boundary. Setting the app to external ingress does not make an internal-only environment internet-accessible. If your environment is internal-only, an accessible web environment plus private connectivity, or a public gateway, is a separate networking prerequisite. [Ingress behavior](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).

### Step 11. Create or reuse a container registry

If you already have Azure Container Registry, reuse it. Otherwise, in the Azure portal:

1. Search for **Container registries** and select **Create**.
2. Select your subscription and resource group, choose a globally unique registry name, and select an appropriate region.
3. Complete creation and record the **Login server**, such as `myregistry.azurecr.io`.

The registry stores the image; it does not run the application. [Registry creation guide](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-get-started-portal).

### Step 12. Build and upload the application image

In PowerShell, from the project root:

```powershell
Set-Location 'D:\learning\langchain\rag_app_foundry'
az login
az account set --subscription '<your-subscription-id>'
az acr build --registry '<registry-name>' --image 'rag-web:v1' .
```

Use the registry's short **name**, not its full login server, for `--registry`. The final `.` is the project directory containing the Dockerfile.

This uploads the Docker build context, builds in Azure and stores `REGISTRY.azurecr.io/rag-web:v1`. Your account needs permission to run registry builds. ACR Tasks may incur charges. **Local Docker Desktop is not required for this command.** [ACR cloud-build documentation](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-quickstart-task-cli).

The existing Dockerfile builds the frontend and installs locked Python dependencies. `.dockerignore` excludes local secrets and data from the context. Wait for the build to finish successfully before continuing. In the registry, open **Repositories → rag-web** and confirm tag `v1` exists.

Optional local image check, if you prefer to test Docker first:

```powershell
docker build --tag rag-web:local .
```

A successful local build alone does not upload anything to Azure. Continue with the ACR build above to publish the image. No completed Docker image build is assumed by this guide.

### Step 13. Create the web Container App in the portal

A temporary quickstart image makes the manual identity and URL setup straightforward:

1. Search for **Container Apps → Create → Container App**.
2. Select the intended subscription/resource group and name it `rag-web`.
3. Select **Container image** as the deployment source.
4. Select the **existing Container Apps environment** used by Chroma and its region.
5. Choose the portal's **quickstart/hello-world image** temporarily.
6. Enable **HTTP ingress** with external access. Use the quickstart image's target port, normally `80`, for this temporary revision.
7. Select **Review + create**, then **Create**.
8. Open the resource and copy its **Application URL**, for example `https://rag-web.<environment-domain>.azurecontainerapps.io`.

At this point the URL shows the placeholder application. The next steps replace that image with your RAG app. Do not use the existing Chroma app as the deployment target. [Portal creation guide](https://learn.microsoft.com/en-us/azure/container-apps/quickstart-portal).

### Step 14. Allow the web app to pull its private image

For a straightforward manual setup:

1. On the new web Container App, open **Identity → System assigned**.
2. Set the status to **On** and save.
3. In the registry, open **Access control (IAM) → Add role assignment**.
4. For a registry using standard registry RBAC, assign **AcrPull** to that Container App's managed identity.

For an ABAC-enabled registry, use its repository-reader role and appropriate scope instead of assuming `AcrPull` applies. If your current deployment already uses a user-assigned identity, attach that identity under **Identity → User assigned** and use it for registry access instead. Your account needs permission to assign these roles.

Image-pull identity is separate from browser sign-in and does not change user-token validation. [Managed identity image pulls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull), [ACR roles](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-built-in-roles-overview).

### Step 15. Transfer the existing runtime settings

Azure does not automatically load your PC's `.env` or inherit your Foundry project connections.

On the web Container App, add needed sensitive values under **Secrets** first. Then use **Containers → Edit and deploy** (or **Revision management → Create new revision**, depending on the portal layout) to configure the image and its environment variables.

Keep the current authentication method:

| Current method | What to configure in Azure |
| --- | --- |
| Foundry/embedding API keys | Store the same applicable keys as Container App secrets; reference them through `FOUNDRY_API_KEY` and `AZURE_OPENAI_API_KEY` |
| `DefaultAzureCredential` with no model key | Attach a managed identity with inference access to the model resources; the container cannot use your PC's `az login` session |
| Existing Chroma authentication header | Store `CHROMA_AUTH_TOKEN` as a secret and preserve `CHROMA_AUTH_HEADER` |
| Existing browser access-token authentication | Copy the non-secret `AUTH_*` settings unchanged |

When using managed identity for Azure OpenAI model calls, grant **Cognitive Services OpenAI User** on each backing chat/embedding resource. For a user-assigned identity, set `AZURE_CLIENT_ID` to its client ID and attach it to the app. For system-assigned identity, leave `AZURE_CLIENT_ID` unset. This supplies cloud credentials to the existing code; no authentication-code change is required. [Azure model identity configuration](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/managed-identity).

Use these deployment settings:

| Variable | Azure value |
| --- | --- |
| `APP_ENV` | `production` |
| `PUBLIC_ORIGIN` | Your copied HTTPS Application URL, without a trailing slash |
| `FOUNDRY_OPENAI_ENDPOINT` | Same working chat endpoint ending in `/openai/v1/` |
| `FOUNDRY_CHAT_MODEL` | Same chat deployment name |
| `AZURE_OPENAI_ENDPOINT` | Same embedding resource endpoint |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Same embedding deployment used for the stored vectors |
| `AZURE_OPENAI_API_VERSION` | Existing working version |
| `CHROMA_URL` | Existing Chroma URL reachable from this Container Apps environment |
| `CHROMA_COLLECTION`, `CHROMA_TENANT`, `CHROMA_DATABASE` | Same intended collection, tenant and database |
| `AUTH_AUTHORITY`, `AUTH_ISSUER`, `AUTH_JWKS_URL` | Existing identity-provider values |
| `AUTH_AUDIENCE`, `AUTH_SPA_CLIENT_ID`, `AUTH_SCOPE`, `AUTH_REQUIRED_SCOPE` | Existing application/scope values |

Environment variables can reference Container App secrets; do not place key values in the image or browser configuration. [Environment variable settings](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables), [Container App secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets).

For your existing browser sign-in to return to the new URL, add `https://<your-app-FQDN>/` to the existing SPA registration's allowed redirect URIs. Keep the local redirect URI for local development. This is a deployment URL registration; the issuer, audience, scopes and token-validation logic remain the same. [MSAL redirect URI configuration](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/initialization).

### Step 16. Deploy the real image and configure port 8000

In the new revision's container settings:

| Field | Value |
| --- | --- |
| Image source | Azure Container Registry |
| Registry | Your registry |
| Image/repository | `rag-web` |
| Tag | `v1` |
| Registry authentication | Managed identity configured in Step 14 |
| CPU / memory | Start with `1 CPU` / `2 GiB` |
| Command / arguments override | Leave empty; use the Dockerfile's startup command |

Set the web app's ingress **target port to `8000`** for the real image. Keep HTTP ingress external, with insecure HTTP disabled. The Dockerfile already starts Uvicorn on `0.0.0.0:8000`; do not use the local-only `127.0.0.1` bind inside Azure.

Configure HTTP health probes for the actual image, all on port `8000`:

| Probe | Path | Period | Timeout | Failure threshold |
| --- | --- | --- | --- | --- |
| Startup | `/health/live` | 5 seconds | 3 seconds | 60 |
| Liveness | `/health/live` | 30 seconds | 3 seconds | 3 |
| Readiness | `/health/ready` | 30 seconds | 25 seconds | 3 |

Under scaling, initially set **minimum replicas = 1** and **maximum replicas = 1**. Keep the Dockerfile's one Uvicorn worker because the current rate limits are per process. The existing deployment template provides these same reference settings if you later choose infrastructure-as-code.

Save and deploy the revision. In **Revision management**, confirm the real-image revision becomes healthy and receives the web app's traffic. If multiple revisions are enabled, explicitly direct traffic to the intended healthy revision. The placeholder revision is not proof that your Python app is running. [Health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes).

### Step 17. Verify Chroma connectivity and persistence

Confirm that:

1. The web and Chroma apps are in the intended environment/network.
2. `CHROMA_URL` resolves from the web app and points to the Chroma service, not to `localhost` or a directory path.
3. The collection name, tenant and database match the existing stored data.
4. Chroma's persistent volume and server data path remain as previously configured.

Use the internal Chroma FQDN when its ingress is limited to the Container Apps environment. That restriction can prevent direct local-PC access, so retain an appropriate private path for administration and ingestion. The browser sends requests to your API; it does not need direct access to Chroma.

Do not rerun ingestion on web-app startup. You do not need to copy PDFs or database files into the web image when the documents are already indexed.

### Step 18. Run the deployed application from the internet

Open the web Container App's HTTPS Application URL. Azure runs the server continuously according to its replica settings; you do not run `uvicorn` manually after deployment.

From PowerShell:

```powershell
$ragAppUrl = 'https://YOUR-WEB-APP-FQDN'
Invoke-RestMethod "$ragAppUrl/health/live"
Invoke-RestMethod "$ragAppUrl/health/ready"
```

Expected: `ok` and `ready`. Then sign in through the browser and ask a question with a known answer in the documents. Verify that the answer and supporting document/page references are sensible.

If you call `POST /api/chat` directly, it still requires a valid API access token from your existing sign-in flow. A model API key, ID token, or generic Azure CLI token is not a substitute. An unauthenticated call returning **401** is expected.

To inspect problems, open the web Container App's **Log stream** and **Revision management**. CLI alternative:

```powershell
az containerapp logs show --name 'rag-web' --resource-group '<app-resource-group>' --type console --follow
```

Press **Ctrl+C** to stop watching logs; this does not stop the deployed app.

### Step 19. Deploy a later code update

After making and testing a future code change, build a new tag:

```powershell
az acr build --registry '<registry-name>' --image 'rag-web:v2' .
```

In the web app, choose **Edit and deploy**, select tag `v2`, keep the working configuration, and deploy a new revision. Verify health and a signed-in question before directing traffic to it. Keep the previous image/tag available for rollback. Updating the web image should not replace Chroma or its storage.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `No module named app` | Run from the project root and use the documented module commands |
| `No Python at ...` | The virtual environment may refer to a missing interpreter; verify Python 3.12 and rebuild the environment with uv if necessary |
| Missing `AUTH_*` configuration at startup | Browser auth remains required; use the terminal pipeline while deferring web-auth configuration |
| Browser says to build the frontend | Run `npm.cmd --prefix web ci` and `npm.cmd --prefix web run build` |
| Azure CLI credentials unavailable locally | Run `az login` for the resource tenant, or use the existing configured model key |
| Model 401/403 in Azure | Check the applicable key secret or attached identity and model-resource role assignments |
| Browser 401/403 | Check the existing token's issuer, audience, scope, expiry and authorized SPA client; do not use a model key as a user token |
| Redirect mismatch | Register the exact browser URL, including the redirect path/trailing slash; match `PUBLIC_ORIGIN` |
| Image pull error | Check repository/tag, registry reachability, selected pull identity and its registry role |
| App won't start in Azure | Check required environment settings and logs; confirm the image's startup command was not overridden |
| Wrong page or placeholder still appears | Check which image/revision receives traffic and whether ingress targets port 8000 |
| Readiness returns 503 | Check Chroma reachability and the existence/nonempty state of the configured collection |
| Chat returns 503 while readiness succeeds | Check embedding/chat permissions, endpoint values, model availability and embedding dimension compatibility |
| Chat returns 504 | A request exceeded the application's total timeout; inspect upstream latency and load |
| 429 response | Respect the retry interval; the app or model service may be rate-limiting requests |
| Embedding dimension mismatch | Use the original embedding deployment or rebuild a separate collection for the new model |
| Model cannot answer a question | Confirm the information is actually in the indexed documents; a successful deployment does not guarantee retrieval quality |

## If you specifically want to host the backend inside Foundry Agent Service

Foundry hosted agents are a separate deployment target. They require code that implements a supported agent-hosting protocol. The current `app.main:app` HTTP API and its Dockerfile are for a general web server.

The future migration sequence would be:

1. Choose the supported hosted-agent protocol and hosting SDK from the official quickstart.
2. Add an agent entry point that calls this app's RAG service and adapts requests/responses to that protocol.
3. Configure model access and a supported network path to Chroma. An agent hosted elsewhere cannot automatically reach Chroma's environment-only ingress.
4. Package/deploy the adapted source or container using Foundry's supported tooling and verify its agent endpoint.
5. Update the web backend/client integration to call that endpoint. A public browser UI still needs a web hosting surface.

That requires additional code changes, so it is **not** part of this instructions-only guide. Do not upload the existing web image as a hosted agent and expect it to work unchanged. Follow Microsoft's [deploy-your-own-code quickstart](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-deploy-own-code) for that migration.

For the application as it exists now, complete **Part 1**, then **Part 2**: the website runs on Container Apps and continues using your models in Foundry.
