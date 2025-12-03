🔐 Verge Auth SDK
Plug-and-Play Central Authentication for FastAPI & Microservices

Verge Auth SDK is a production-ready authentication & authorization middleware designed for microservices, SaaS platforms, and enterprise systems that require:

Centralized login

Role-based access control (RBAC)

Dynamic permissions

Secure service-to-service validation

Automated microservice route discovery

With one line of code, your service becomes fully authenticated:

from verge_auth_sdk import add_central_auth
add_central_auth(app)

🚀 Key Features
🔑 Centralized Authentication

All microservices share a unified login system via Verge Auth Server.

🧠 Intelligent Token Handling

Validates JWT access tokens

Supports cookies (browser) and headers (API clients)

Automatically redirects HTML clients to login

🔒 RBAC (Role Based Access Control)

Role-aware request context is attached to each request:

request.state.user
request.state.roles

🌐 Multi-Service Support

Perfect for:

HRMS

ERP

CRM

Billing

Appointment systems

Admin dashboards

🤖 Automated Microservice Route Discovery

The SDK automatically exposes all your microservice’s routes through:

GET /**verge**/routes

These routes are:

Synced into Verge Auth Server

Used for RBAC configuration

Visible in the RBAC UI for assigning permissions

Automatically validated on every request

🛡 Service-to-Service Secret Validation

Each microservice must present:

X-Verge-Service-Secret: <shared-secret>

This prevents fake/rogue services from registering routes or bypassing auth.

🏗 Architecture Overview
User → Client App
↓
Verge Auth SDK Middleware
↓
Verge Auth Server (Introspection / RBAC)
↓
Allow / Reject

Example URLs:

Component URL
Auth Backend API https://xyz.com/api

Login UI https://xyz.com/login

Client Application https://clientapp.com
📦 Installation
From PyPI
pip install verge_auth_sdk

From GitHub
pip install git+https://github.com/verge-infosoft/verge-auth.git

⚙️ Environment Configuration

Add the following to your service’s .env file:

🔐 Core Authentication
AUTH_INTROSPECT_URL=https://xyz.com/api/introspect
AUTH_LOGIN_URL=https://xyz.com/login

🆔 Client Credentials
VERGE_CLIENT_ID=your_client_id
VERGE_CLIENT_SECRET=your_client_secret

🔐 Critical Setting — REQUIRED

Shared Service Secret (MANDATORY)

VERGE_SERVICE_SECRET=<your-shared-secret>

⚠️ Required for:

Automated microservice route discovery

Registering routes inside RBAC UI

Securing /**verge**/routes

Service-to-service authentication

Preventing unauthorized microservices

👉 Without this secret, automated route discovery WILL NOT WORK.
👉 Contact Verge Infosoft to obtain your unique VERGE_SERVICE_SECRET.

🔐 Secret Provider Options
SECRETS_PROVIDER=env # env | azure | aws
AZURE_KEY_VAULT_URL=unused
AWS_REGION=unused

🚀 One-Line Integration
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()
add_central_auth(app)

That’s it. ✔
Your service is now centrally authenticated.

🔄 Authentication Flow
1️⃣ User opens a protected page
GET https://clientapp.com/employees

2️⃣ No token found → redirect to Login UI
https://xyz.com/login?redirect_url=https://clientapp.com/employees

3️⃣ After login → redirected back with token
https://clientapp.com/employees?token=<JWT_TOKEN>

4️⃣ SDK validates token via introspection
POST /introspect

5️⃣ Access granted or denied
🔌 Automated Route Discovery

SDK automatically discovers all routes at startup:

GET /**verge**/routes

Used for:

Syncing routes with Verge Auth Server

Dynamic RBAC assignment

Microservice-level permission control

Example output:

[
{"path": "/employees/", "method": "POST"},
{"path": "/employees/{id}", "method": "GET"},
{"path": "/health", "method": "GET"}
]

🧑‍💼 Role-Based Access Control (RBAC)

Verge Auth Server allows assigning permissions per route:

Role Access
Super Admin All services + admin dashboard
Admin Everything except super-admin controls
User Redirected to assigned application UI
Custom Roles Supported

Dynamic RBAC is managed in the UI — no code changes needed.

🧰 Middleware Behavior

The SDK automatically:

✔ Validates JWT tokens
✔ Accepts cookies or Authorization header
✔ Redirects HTML clients to login
✔ Returns 401 Unauthorized for APIs
✔ Provides user + roles to each request
✔ Supports service-to-service authentication
✔ Whitelists internal system routes

🔐 Security Features

RSA-based JWT (RS256)

Client ID / Secret validation

Token expiry enforcement

Role-aware access restriction

Encrypted service-secret validation

Secure HTTPS communication

Ready for distributed caching (Redis)

🌍 Example Use Cases
Example: /employee
Role Behavior
Super Admin Global admin dashboard
Admin Limited admin screen
User Redirected to user UI
❓ FAQ
Do I need to host authentication myself?

❌ No — Verge Auth is hosted for you.
Self-hosting is available for enterprise plans.

Does it support microservices?

✔ Built specifically for microservices.

Does it support multi-tenant SaaS?

✔ Yes, natively.

🆘 Support

For integration help:

🌐 Website
https://www.vergeinfosoft.com

📧 Email
contactus@vergeinfosoft.com
