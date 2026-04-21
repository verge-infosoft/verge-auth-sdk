# Verge Auth IAM Engine

# Getting Started with Verge Auth

> Think of Verge Auth as a **security guard for your app**.  
> You tell it which pages need login and who can access what — it handles everything else.

---

## Before You Start

1. Register HRMS at [app.vergeauth.in](https://app.vergeauth.in/register)
2. Securely store the following credentials:
   - `CLIENT_ID`
   - `CLIENT_SECRET`
   - `SERVICE_SECRET`

---

## How Login Works

```
User opens HRMS
       ↓
Not logged in? → Redirected to Verge Auth login page
       ↓
User logs in
       ↓
Redirected back to HRMS — now logged in ✅
       ↓
Verge Auth manages page and API access
```

HRMS does not handle passwords or permissions directly. Verge Auth manages all security aspects.

---

## What You Need to Do

| Where        | What                                          | Lines of code |
|--------------|-----------------------------------------------|---------------|
| Backend      | Install SDK + one line of code                | 2             |
| Backend      | Add `.env` with credentials                   | 1 file        |
| Frontend     | Add page guard to `index.html`                | 1 line        |
| Frontend     | Create 4 small files (copy-paste)             | 4 files       |
| Frontend     | Add `.env` with login URL                     | 1 file        |
| Nginx        | Proxy `/api/` to backend                      | 4 lines       |
| Dashboard    | Create roles and assign to users              | No code       |

---

## Step 1 — Backend: Install the SDK

```bash
pip install verge_auth_sdk
```

Add it to your FastAPI app — **one import, one function call as the last line**:

```python
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()

@app.get("/api/employees")
def list_employees():
    return []

# IMPORTANT: Must be the last line in your app
add_central_auth(app)
```

**That's it for backend code. No JWT. No decorators. No permission checks.**

---

## Step 2 — Backend: Add a `.env` file

Create a `.env` file next to your `main.py`:

```env
# Verge Auth service URLs
AUTH_FRONTEND_URL=https://app.vergeauth.in
AUTH_BASE_URL=https://api.vergeauth.in

# Your application
SERVICE_NAME=hrms
SERVICE_BASE_URL=https://api.yourdomain.com
SERVICE_FRONTEND_URL=https://app.yourdomain.com

# Credentials (from Verge Auth dashboard)
VERGE_CLIENT_ID=<your client id>
VERGE_CLIENT_SECRET=<your client secret>
VERGE_SERVICE_SECRET=<your service secret>

# Routes that don't require login
PUBLIC_PATHS=["/health"]
```

> **For local development**, use:
> ```env
> AUTH_FRONTEND_URL=http://localhost:5173
> AUTH_BASE_URL=http://localhost:8000
> SERVICE_BASE_URL=http://localhost:8001
> SERVICE_FRONTEND_URL=http://localhost:5174
> ```

---

## Step 3 — Frontend: Add the Page Guard (1 line)

Open your `index.html` and add **one script tag** before your app:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HRMS</title>
  </head>
  <body>
    <!-- Verge Auth page guard — blocks unauthorized pages automatically -->
    <script src="/api/auth/page-guard.js"></script>

    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

**What this does:**
- Checks if the logged-in user has permission to view the current page
- If yes — the page loads normally
- If no — shows a styled "Access Denied" screen and redirects to an allowed page
- If not logged in — lets your app's own login flow handle it

You don't write any permission logic. The script is served by the SDK and works automatically.

---

## Step 4 — Frontend: Create 4 Small Files

### 4a. API Client

Create `src/services/api.js`:

```js
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,  // required — sends auth cookies with every request
});

export default api;
```

---

### 4b. Auth State

Create `src/context/AuthContext.jsx`:

```jsx
import { createContext, useContext, useEffect, useState } from "react";
import api from "../services/api";

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/auth/me")
      .then(() => setIsAuthenticated(true))
      .catch(() => setIsAuthenticated(false))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

> `/auth/me` is provided by the SDK — you don't need to build it.

---

### 4c. Protected Route Wrapper

Create `src/components/ProtectedRoute.jsx`:

```jsx
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { loading, isAuthenticated } = useAuth();

  if (loading) return <div>Checking authentication...</div>;

  if (!isAuthenticated) {
    window.location.href =
      import.meta.env.VITE_VERGEAUTH_LOGIN_URL +
      "?redirect_uri=" + window.location.origin + "/auth/callback";
    return null;
  }

  return children;
}
```

---

### 4d. Login Callback Page

Create `src/pages/AuthCallback.jsx`:

```jsx
import { useEffect } from "react";
import api from "../services/api";

export default function AuthCallback() {
  useEffect(() => {
    const finishLogin = async () => {
      const code = new URLSearchParams(window.location.search).get("code");

      // Exchange the login code for a session
      try {
        if (code) await api.post("/auth/exchange", { code });
      } catch (err) {
        console.error("Auth exchange failed", err);
      }

      // Redirect to the first page this user is allowed to access
      try {
        const res = await api.get("/auth/accessible-routes");
        const pages = res.data.accessible_routes || [];
        window.location.href = pages[0] || "/";
      } catch {
        window.location.href = "/";
      }
    };

    finishLogin();
  }, []);

  return <div>Signing you in...</div>;
}
```

> The SDK figures out which pages the user can access based on their role.  
> No need to hardcode a redirect URL — it's fully dynamic.

---

### 4e. Frontend `.env` 

Create `.env` in your frontend root:

```env
VITE_VERGEAUTH_LOGIN_URL=https://app.vergeauth.in/login
```

For local development:
```env
VITE_VERGEAUTH_LOGIN_URL=http://localhost:5173/login
```

---

## Step 5 — Wire It Together in Your Router

```jsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AuthCallback from "./pages/AuthCallback";
import Employees from "./pages/Employees";
import Attendance from "./pages/Attendance";
import Leaves from "./pages/Leaves";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Home />} />
          <Route path="/auth/callback" element={<AuthCallback />} />

          {/* Protected routes — wrap with ProtectedRoute */}
          <Route path="/employees" element={
            <ProtectedRoute><Employees /></ProtectedRoute>
          } />
          <Route path="/attendance" element={
            <ProtectedRoute><Attendance /></ProtectedRoute>
          } />
          <Route path="/leaves" element={
            <ProtectedRoute><Leaves /></ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

Wrap `<AuthProvider>` around your entire app in `main.jsx`:

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);
```

---

## Step 6 — Nginx: Forward API Calls to Your Backend

Add this to your `nginx.conf`:

```nginx
server {
  listen 80;

  root /usr/share/nginx/html;
  index index.html;

  # Serve frontend (SPA fallback)
  location / {
    try_files $uri /index.html;
  }

  # Forward all /api/ requests to your backend
  location /api/ {
    proxy_pass http://your-backend:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cookie_path / "/; SameSite=None; Secure";
  }
}
```

> Replace `your-backend:8001` with your actual backend service name and port.

---

## Step 7 — Roles & Permissions (No Code Needed)

Once HRMS is running, all API routes appear in the Verge Auth dashboard **automatically**.

1. Go to **Roles** → **New Role**
2. Name it (e.g. `HR Manager`, `Billing Admin`)
3. Pick which routes this role can access (checkboxes)
4. Assign the role to a user or group

**Done.** The user will only be able to access the routes you allowed.  
Change permissions anytime from the dashboard — no code deploy needed.

---

## Who Logged In? (Optional)

If HRMS needs to know which user made a request:

```python
from fastapi import Request

@app.get("/api/employees")
def list_employees(request: Request):
    auth = request.state.auth

    print(auth["user_id"])           # who is this user?
    print(auth["organization_id"])   # which organization?
    print(auth.get("tenant_id"))     # which tenant? (multi-tenant apps)
    print(auth["scope"])             # what scope?
    print(auth["roles"])             # what permissions?

    return []
```

This is injected by the Verge Auth SDK — **cryptographically verified and safe to trust**.

---

## How Security Works — Two Layers

Verge Auth protects HRMS at **two levels** automatically:

### Layer 1 — API Protection (Backend)
Every API request (`/api/*`) passes through the SDK middleware.  
If the user doesn't have the required permission → **403 Forbidden**.

### Layer 2 — Page Protection (Frontend)
The page guard script checks if the user can view the current page.  
If not → **styled "Access Denied" screen** with redirect options.

```
User navigates to /employees
         ↓
   Page guard checks permissions
         ↓
  ┌──────────────────────┐
  │ Has permission?      │
  │   YES → page loads   │
  │   NO  → Access Denied│
  └──────────────────────┘
```

Both layers work together. Even if someone bypasses the frontend, the backend always enforces permissions.

---

## Quick Checklist

- [ ] Register at [app.vergeauth.in](https://app.vergeauth.in) and get credentials
- [ ] Backend: `pip install verge_auth_sdk` 
- [ ] Backend: add `add_central_auth(app)` as the **last line**
- [ ] Backend: create `.env` with credentials and URLs
- [ ] Frontend: add `<script src="/api/auth/page-guard.js"></script>` to `index.html` 
- [ ] Frontend: create `api.js` with `withCredentials: true` 
- [ ] Frontend: create `AuthContext.jsx` 
- [ ] Frontend: create `ProtectedRoute.jsx` 
- [ ] Frontend: create `AuthCallback.jsx` 
- [ ] Frontend: create `.env` with `VITE_VERGEAUTH_LOGIN_URL` 
- [ ] Frontend: add `/auth/callback` route and wrap pages with `ProtectedRoute` 
- [ ] Nginx: proxy `/api/` to backend
- [ ] Dashboard: create roles → assign permissions → assign to users

---

## What You Don't Need to Do

- ❌ Handle passwords or tokens
- ❌ Write JWT validation code
- ❌ Add permission decorators to routes
- ❌ Build a login page
- ❌ Manage sessions
- ❌ Write role-checking logic

**You focus on building HRMS. Verge Auth handles identity and security.**

---

## Need Help?

|   |   |
|---|---|
| 📖 Docs | [vergeinfosoft.com/docs](https://vergeinfosoft.com/docs) |
| 📧 Email | contactus@vergeinfosoft.com |
| 🌐 Website | [vergeinfosoft.com](https://www.vergeinfosoft.com) |

---

*Verge Auth — You build features. We handle login and security.*
