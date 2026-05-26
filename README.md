# Verge Auth SDK

**Secure Identity & Access Management for FastAPI Microservices**

Verge Auth SDK connects your FastAPI application to the **Verge Auth Platform** — providing centralized login, role-based access control, and route-level permissions with a single line of code.

```python
from verge_auth_sdk import add_central_auth
add_central_auth(app)
```

---

## Quick Start (5 Minutes)

### Step 1: Install

```bash
pip install verge_auth_sdk
```

### Step 2: Add to your FastAPI app

```python
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()

# Your routes here...

# IMPORTANT: This must be the LAST line in your main.py
add_central_auth(app)
```

### Step 3: Configure environment variables

Create a `.env` file (or set these in your deployment):

```env
# ─── VERGE AUTH PLATFORM (DO NOT CHANGE) ───────────────────────────
AUTH_BASE_URL=https://api.vergeauth.in

# ─── YOUR SERVICE CREDENTIALS (provided during onboarding) ─────────
VERGE_CLIENT_ID=<your-client-id>
VERGE_CLIENT_SECRET=<your-client-secret>
VERGE_SERVICE_SECRET=<your-service-integration-secret>

# ─── YOUR SERVICE DETAILS ──────────────────────────────────────────
SERVICE_NAME=<your-service-name>
SERVICE_BASE_URL=<your-backend-url>
SERVICE_FRONTEND_URL=<your-frontend-url>
```

**That's it.** Your service is now protected.

---

## How It Works

### Authentication Flow

```
User → vergeauth.in/login → Verge Auth Dashboard → "Launch" service
  → Auth code issued → Redirects to your app with ?code=xxx
  → SDK exchanges code for JWT → Sets httponly cookie (verge_access)
  → All subsequent requests verified via JWT
```

### What Happens on Startup

When your app starts, the SDK automatically:

1. **Fetches the public key** from Verge Auth (for JWT verification)
2. **Registers your service** with the Verge Auth platform
3. **Syncs all your routes** to the Verge Auth dashboard (so admins can assign permissions)

### What Happens on Every Request

1. **Extracts token** from `verge_access` cookie or `Authorization: Bearer` header
2. **Verifies JWT signature** using the platform's public key
3. **Checks route permission** — the JWT contains a `permissions` array with entries like `service-name:/api/path:method`
4. **Grants or denies** access (403 if permission missing)

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `AUTH_BASE_URL` | Yes | Verge Auth API endpoint (always `https://api.vergeauth.in`) |
| `VERGE_CLIENT_ID` | Yes | Your client ID (provided during onboarding) |
| `VERGE_CLIENT_SECRET` | Yes | Your client secret (provided during onboarding) |
| `VERGE_SERVICE_SECRET` | Yes | Service integration secret (provided during onboarding) |
| `SERVICE_NAME` | Yes | Must match exactly what's registered in Verge Auth dashboard (e.g., `hrms-service`) |
| `SERVICE_BASE_URL` | Yes | Your backend's public URL (e.g., `https://api.yourapp.com`) |
| `SERVICE_FRONTEND_URL` | Yes | Your frontend's public URL (e.g., `https://app.yourapp.com`) |
| `PUBLIC_PATHS` | No | JSON array of paths that don't require authentication (e.g., `["/health", "/docs"]`) |
| `SECRETS_PROVIDER` | No | Secret provider: `env` (default), `aws`, `azure`, `gcp`, `oracle` |

---

## Permission System

### How Permissions Work

Permissions are **route-level keys** in the format:

```
<service-name>:<path>:<method>
```

**Examples:**
- `hrms-service:/api/employees:get` — Can list employees
- `hrms-service:/api/employees:post` — Can create employees
- `hrms-service:/api/dashboard/stats:get` — Can view dashboard
- `hrms-service:/api/auth/me:get` — Can access the auth/me endpoint (required for all users)

### Important: The `/auth/me` Permission

Every role that accesses your service **must** have the `/api/auth/me GET` permission assigned. This is the baseline "can access this service" gate. Without it, users cannot authenticate.

### Wildcard Permission

Users with `PLATFORM_OWNER` role receive `permissions: ["*"]` which grants access to all routes without needing individual assignments.

---

## Frontend Integration Guide

### Required: `/auth/me` Endpoint

Your backend needs a simple endpoint that returns the authenticated user's context:

```python
from fastapi import APIRouter, Request

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.get("/me")
def get_current_user(request: Request):
    return request.state.auth
```

This returns:
```json
{
  "auth_user_id": 1,
  "organization_id": 1,
  "tenant_id": null,
  "scope": "platform",
  "roles": ["HR Manager"],
  "permissions": [
    "hrms-service:/api/auth/me:get",
    "hrms-service:/api/employees:get",
    "hrms-service:/api/dashboard/stats:get"
  ]
}
```

### Frontend Auth Context (React Example)

```javascript
// AuthContext.jsx
import { createContext, useContext, useEffect, useState } from "react";
import api from "../services/api";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [permissions, setPermissions] = useState([]);

  useEffect(() => {
    api.get("/auth/me")
      .then((res) => {
        setIsAuthenticated(true);
        setPermissions(res.data.permissions || []);
      })
      .catch((err) => {
        if (err.response && err.response.status === 403) {
          setIsAuthenticated(true); // authenticated but missing route permission
        } else {
          setIsAuthenticated(false);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const hasPermission = (permission) => {
    return permissions.some(p => p.toLowerCase() === permission.toLowerCase());
  };

  const hasAnyPermission = (permissionList) => {
    return permissionList.some(perm =>
      permissions.some(p => p.toLowerCase() === perm.toLowerCase())
    );
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading, permissions, hasPermission, hasAnyPermission }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

### Route Protection (React Example)

```javascript
// ProtectedRoute.jsx
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, requiredPermissions = [] }) {
  const { loading, isAuthenticated, hasAnyPermission } = useAuth();

  if (loading) return <div>Loading...</div>;

  if (!isAuthenticated) {
    window.location.href = "https://vergeauth.in/login?redirect_url=" +
      encodeURIComponent(window.location.origin + "/auth/callback");
    return null;
  }

  if (requiredPermissions.length > 0 && !hasAnyPermission(requiredPermissions)) {
    return <div>Access Denied</div>;
  }

  return children;
}
```

### Auth Callback Page

```javascript
// AuthCallback.jsx — handles the ?code= redirect from Verge Auth
import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const code = params.get("code");
    if (code) {
      // Hit backend with code — SDK middleware will exchange it and set cookie
      api.get(`/auth/callback?code=${code}`)
        .then(() => navigate("/"))
        .catch(() => navigate("/"));
    }
  }, []);

  return <div>Authenticating...</div>;
}
```

### Axios Configuration

```javascript
// api.js
import axios from "axios";

const api = axios.create({
  baseURL: "/api",        // proxied to backend
  withCredentials: true,  // REQUIRED: sends httponly cookies
});

export default api;
```

### Nginx Configuration (Frontend + Backend)

```nginx
server {
    listen 80;
    server_name app.yourservice.com;

    # Frontend
    location / {
        proxy_pass http://frontend:80;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Auth callback (SDK intercepts ?code=)
    location /auth/callback {
        proxy_pass http://backend:8001/auth/callback;
        proxy_set_header Host $host;
    }

    # Logout — clears the httponly cookie at nginx level
    location /auth/logout {
        add_header Set-Cookie "verge_access=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" always;
        return 302 https://vergeauth.in/login;
    }
}
```

> **Important:** The SDK sets `verge_access` as an httponly cookie — JavaScript cannot clear it. Logout must be handled at the Nginx level.

---

## Setting Up Roles in Verge Auth Dashboard

### Step 1: Create a Role

1. Go to **Roles** → **New Role**
2. Enter role name (e.g., `HR Manager`)
3. Select the **Service** (e.g., `hrms-service`)
4. The system shows all synced routes with methods
5. Check the routes this role should access
6. **Always include** `/api/auth/me GET` for any role that accesses the service
7. Save

### Step 2: Assign Role to Users

**Direct assignment:**
- Go to **Users** → Edit user → Select roles → Save

**Via Group (recommended for teams):**
- Create a group (e.g., `HR Team`)
- Assign roles to the group
- Add users to the group — they inherit all group permissions automatically

### Minimum Required Permissions for Any Service Role

| Route | Method | Why |
|-------|--------|-----|
| `/api/auth/me` | GET | Required for authentication check |
| `/api/<page-endpoint>` | GET | The page(s) the user should see |

---

## Key Notes

- **`SERVICE_NAME` must match exactly** between your env var and the Verge Auth dashboard (e.g., `hrms-service`, not `hrms`)
- **Login URL uses `redirect_url`** param (not `redirect_uri`)
- **SDK checks ALL routes** including `/auth/me` — 403 means authenticated but missing that specific route permission
- **Permissions come from both direct roles AND group-inherited roles**
- **Cookie is httponly** — logout must clear it at the web server level (Nginx)
- **Routes sync automatically** on service startup — no manual registration needed

---

## Security Highlights

- RS256 asymmetric JWT verification (no shared secret between services)
- Persistent key management with key rotation support
- httponly, secure cookies for token storage
- Service-to-service authentication via client credentials
- Multi-layer permission checks: Role → Service → Route → Method
- Support for cloud secret vaults (AWS, Azure, GCP, Oracle)

---

## Support

For onboarding, custom integrations, or troubleshooting:

- **Website:** https://www.vergeinfosoft.com
- **Email:** contactus@vergeinfosoft.com
