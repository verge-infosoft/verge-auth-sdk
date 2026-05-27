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

## Enterprise Security & Access Enforcement

Verge Auth automatically secures protected application routes, validates authenticated sessions, and enforces centralized authorization policies across your services.

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

Verge Auth supports fine-grained, route-aware authorization policies aligned with your application structure.

---

## Frontend Integration Guide

### User Context Endpoint

Applications should expose an authenticated user context endpoint for frontend session awareness.

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
  "roles": ["HR Manager"]
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
  const [user, setUser] = useState(null);

  useEffect(() => {
    api.get("/auth/me")
      .then((res) => {
        setIsAuthenticated(true);
        setUser(res.data);
      })
      .catch((err) => {
        if (err.response && err.response.status === 403) {
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading, user }}>
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

export default function ProtectedRoute({ children, requiredRole }) {
  const { loading, isAuthenticated, user } = useAuth();

  if (loading) return <div>Loading...</div>;

  if (!isAuthenticated) {
    window.location.href = "https://vergeauth.in/login?redirect_url=" +
      encodeURIComponent(window.location.origin + "/auth/callback");
    return null;
  }

  if (requiredRole && !user?.roles?.includes(requiredRole)) {
    return <div>Access Denied</div>;
  }

  return children;
}
```

### Auth Callback Page

```javascript
// AuthCallback.jsx — handles the redirect from Verge Auth
import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "../services/api";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const code = params.get("code");
    if (code) {
      api.get(`/auth/callback?code=${code}`)
        .then(() => navigate("/"))
        .catch(() => navigate("/"));
    }
  }, []);

  return <div>Authenticating...</div>;
}
```

The SDK securely completes authentication and establishes the user session automatically.

### Axios Configuration

```javascript
// api.js
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
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

    # Auth callback
    location /auth/callback {
        proxy_pass http://backend:8001/auth/callback;
        proxy_set_header Host $host;
    }

    # Logout
    location /auth/logout {
        add_header Set-Cookie "verge_access=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" always;
        return 302 https://vergeauth.in/login;
    }
}
```

---

## Setting Up Roles in Verge Auth Dashboard

### Step 1: Create a Role

1. Go to **Roles** → **New Role**
2. Enter role name (e.g., `HR Manager`)
3. Select the **Service** (e.g., `hrms-service`)
4. The system displays available application resources for access configuration.
5. Check the routes this role should access
6. Save

### Step 2: Assign Role to Users

**Direct assignment:**
- Go to **Users** → Edit user → Select roles → Save

**Via Group (recommended for teams):**
- Create a group (e.g., `HR Team`)
- Assign roles to the group
- Add users to the group — they inherit all group permissions automatically

---

## Key Notes

- **`SERVICE_NAME` must match exactly** between your env var and the Verge Auth dashboard (e.g., `hrms-service`, not `hrms`)
- **Login URL uses `redirect_url`** param (not `redirect_uri`)
- Application authorization policies remain synchronized automatically.

---

## Enterprise Features

- **Centralized Authentication** — Single sign-on across all your services
- **Role-Based Access Control** — Granular permissions at the user, group, and role level
- **Audit Logging** — Track authentication events and access attempts
- **SSO & MFA** — Enterprise-grade security with multi-factor authentication
- **Multi-Tenant Support** — Isolate data and permissions across organizations

---

## Security Highlights

- RS256 asymmetric JWT verification (no shared secret between services)
- Persistent key management with key rotation support
- httponly, secure cookies for token storage
- Service-to-service authentication via client credentials
- Support for cloud secret vaults (AWS, Azure, GCP, Oracle)

---

## Support

For onboarding, custom integrations, or troubleshooting:

- **Website:** https://www.vergeinfosoft.com
- **Email:** contactus@vergeinfosoft.com
