# Getting Started with Verge Auth

> Think of Verge Auth as a **security guard for your app**.  
> You tell it which pages need login and who can access what — it handles everything else.

You will make **4 small changes** to your app. That's it.

---

## Before You Start

1. Register your app at [app.vergeauth.in](https://app.vergeauth.in/register)
2. You will receive three credentials — keep them safe:
   - `CLIENT_ID`
   - `CLIENT_SECRET`  
   - `SERVICE_SECRET`

---

## How Login Works (Simple Version)

When a user opens your app:

```
User opens your app
       ↓
Not logged in? → Sent to Verge Auth login page
       ↓
User logs in
       ↓
Sent back to your app — now logged in ✅
       ↓
Every API call is automatically checked by Verge Auth
```

Your app never handles passwords. Verge Auth does all of that.

---

## Step 1 — Backend: Add 2 lines of code

Install the SDK:

```bash
pip install verge_auth_sdk
```

Add it to your FastAPI app — **one import, one line at the bottom**:

```python
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()

@app.get("/api/employees")
def list_employees():
    return []

add_central_auth(app)  # ← always the last line
```

That's it for the backend code. **No JWT. No decorators. No permission checks.**

---

## Step 2 — Backend: Add a `.env` file

Create a `.env` file next to your `main.py`:

```env
AUTH_FRONTEND_URL=https://app.vergeauth.in
AUTH_BASE_URL=https://api.vergeauth.in

SERVICE_NAME=my-app
SERVICE_BASE_URL=https://api.yourdomain.com
SERVICE_FRONTEND_URL=https://app.yourdomain.com

VERGE_CLIENT_ID=<paste your client id here>
VERGE_CLIENT_SECRET=<paste your client secret here>
VERGE_SERVICE_SECRET=<paste your service secret here>

PUBLIC_PATHS=["/health","/docs","/openapi.json","/api/auth/exchange"]
```

> Get your credentials from [app.vergeauth.in](https://app.vergeauth.in) after registering your service.

---

## Step 3 — Frontend: 4 small files

### 3a. Add a `.env` file to your frontend

```env
VITE_VERGEAUTH_LOGIN_URL=https://app.vergeauth.in/login
```

For local dev:
```env
VITE_VERGEAUTH_LOGIN_URL=http://localhost:5173/login
```

---

### 3b. Set up your API client

Create `src/services/api.js`:

```js
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,  // this line is required — don't remove it
});

export default api;
```

---

### 3c. Create an auth state tracker

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

---

### 3d. Protect your pages

Create `src/components/ProtectedRoute.jsx`:

```jsx
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const { loading, isAuthenticated } = useAuth();

  if (loading) return <div>Loading...</div>;

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

### 3e. Handle the login callback

Create `src/pages/AuthCallback.jsx`:

```jsx
import { useEffect } from "react";
import api from "../services/api";

export default function AuthCallback() {
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    api.post("/auth/exchange", { code })
      .finally(() => {
        window.location.href = "/dashboard";  // send user to your home page
      });
  }, []);

  return <div>Signing you in…</div>;
}
```

---

### 3f. Wire it all together in your router

```jsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AuthCallback from "./pages/AuthCallback";
import Employees from "./pages/Employees";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Verge Auth sends the user here after login */}
          <Route path="/auth/callback" element={<AuthCallback />} />

          {/* Wrap any page that needs login with ProtectedRoute */}
          <Route path="/employees" element={
            <ProtectedRoute><Employees /></ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
```

---

## Step 4 — Nginx: Forward API calls to your backend

If you serve your frontend via nginx, add this to your `nginx.conf`:

```nginx
location /api/ {
  proxy_pass http://your-backend:8001;
  proxy_set_header Host $host;
  proxy_cookie_path / "/; SameSite=None; Secure";
}
```

This makes `yourapp.com/api/employees` reach your FastAPI backend automatically.

---

## Step 5 — Roles & Permissions (No Code Needed)

Once your app is running, all your API routes appear in the Verge Auth dashboard automatically.

1. Go to **Roles → New Role**
2. Name it (e.g. `HR Manager`)
3. Pick which routes this role can access
4. Assign the role to a user

Done. The user will only be able to call the routes you allowed. No code change required.

---

## Who Logged In? (Optional)

If you need to know which user made a request, read it from the request:

```python
@app.get("/api/employees")
def list_employees(request: Request):
    user = request.state.auth
    print(user["user_id"])           # who is this?
    print(user["organization_id"])   # which company?
    return []
```

This is injected by Verge Auth — **you can trust it completely**.

---

## Quick Checklist

- [ ] Register app at [app.vergeauth.in](https://app.vergeauth.in) and get credentials
- [ ] Backend: `pip install verge_auth_sdk` → add `add_central_auth(app)` as last line
- [ ] Backend: fill in `.env` with your credentials and URLs
- [ ] Frontend: create `api.js` with `withCredentials: true`
- [ ] Frontend: create `AuthContext.jsx`, `ProtectedRoute.jsx`, `AuthCallback.jsx`
- [ ] Frontend: add `/auth/callback` route (public) and wrap other routes with `ProtectedRoute`
- [ ] Nginx: proxy `/api/` to backend
- [ ] Dashboard: create a role, assign permissions, assign to a user

---

## Need Help?

| | |
|---|---|
| 📖 Docs | [vergeinfosoft.com/docs](https://vergeinfosoft.com/docs) |
| 📧 Email | contactus@vergeinfosoft.com |
| 🌐 Website | [vergeinfosoft.com](https://www.vergeinfosoft.com) |

---

*Verge Auth — You focus on building. We handle login and security.*
