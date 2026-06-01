# Verge Auth SDK

**Enterprise Authentication & RBAC for FastAPI Applications**

Turn your FastAPI routes into enterprise-grade permissions automatically.

Verge Auth provides centralized authentication, role-based access control (RBAC), audit logging, and permission management with minimal integration effort.

---

## Why Verge Auth?

Traditional authentication platforms solve login.

Verge Auth solves **authentication, authorization, and permission management**.

### Key Features

* Centralized Authentication
* Route-Based Permission Generation
* Enterprise RBAC
* Group-Based Access Control
* Audit Logging
* Multi-Tenant Support
* OIDC & SAML Ready
* AI-Powered Security Insights
* FastAPI Native Integration

---

## Installation

```bash
pip install verge_auth_sdk
```

---

## Quick Start

### 1. Add Verge Auth to Your Application

```python
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()

# Your routes

add_central_auth(app)
```

### 2. Configure Environment Variables

```env
AUTH_BASE_URL=https://api.vergeauth.in

VERGE_CLIENT_ID=<client-id>
VERGE_CLIENT_SECRET=<client-secret>
VERGE_SERVICE_SECRET=<service-secret>

SERVICE_NAME=hrms-service
SERVICE_BASE_URL=https://api.example.com
SERVICE_FRONTEND_URL=https://app.example.com
```

### 3. Start Your Application

When the application starts, Verge Auth automatically:

* Registers your service
* Discovers application routes
* Generates route permissions
* Synchronizes permissions with the Verge Auth platform
* Configures JWT validation

Your application is now protected.

---

## How Permission Generation Works

Verge Auth automatically discovers routes in your application and converts them into assignable permissions.

Example:

```python
@app.get("/api/employees")
def list_employees():
    pass

@app.post("/api/employees")
def create_employee():
    pass
```

Automatically generates permissions:

```text
hrms-service:/api/employees:get
hrms-service:/api/employees:post
```

Administrators can assign these permissions through the Verge Auth dashboard without modifying application code.

---

## Authentication Flow

1. User authenticates through Verge Auth.
2. Verge Auth issues an authorization code.
3. SDK exchanges the code for a secure access token.
4. User session is established.
5. Requests are automatically validated.
6. Permissions are enforced on every route.

---

## User Context

Authenticated user information is available inside requests:

```python
from fastapi import Request

@app.get("/auth/me")
def current_user(request: Request):
    return request.state.auth
```

Example response:

```json
{
  "auth_user_id": 1,
  "roles": ["HR Manager"],
  "permissions": [
    "hrms-service:/api/employees:get"
  ]
}
```

---

## Supported Authentication Features

* Local Authentication
* Multi-Factor Authentication (MFA)
* Passwordless Authentication
* OIDC Federation
* SAML Federation
* Microsoft Entra ID Integration
* Google Workspace Integration
* Custom Identity Providers

*Feature availability depends on your Verge Auth plan.*

---

## Security

Verge Auth implements enterprise-grade security practices:

* RS256 JWT Verification
* Automatic Key Rotation Support
* HTTP-Only Secure Cookies
* Service-to-Service Authentication
* Fine-Grained Route Permissions
* Audit Logging
* Multi-Layer Access Control

---

## Documentation

Platform Documentation:

https://vergeinfosoft.com/docs/

Product Guide:

https://vergeinfosoft.com/verge-auth-product-guide/

---

## Support

Website:

https://vergeauth.in

Email:

[contactus@vergeinfosoft.com](mailto:contactus@vergeinfosoft.com)

---

## License

Copyright © Verge Infosoft.

All rights reserved.
