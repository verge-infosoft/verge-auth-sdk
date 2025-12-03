🔐 Verge Auth SDK
Secure Identity & Access Management for FastAPI Microservices

Verge Auth SDK is a lightweight integration library that connects your FastAPI microservices to the Verge Auth Platform — a centralized identity, role management, and access-control system built for modern SaaS applications.

With a single line of code, your service is fully protected and becomes part of a unified authentication ecosystem:

from verge_auth_sdk import add_central_auth
add_central_auth(app)

🚀 What Verge Auth Provides

✓ Centralized Login

Your users authenticate through the Verge Auth hosted login experience.

✓ Role-Based Access Control (RBAC)

Create roles inside the Verge Auth Dashboard and assign access to microservices and their granular operations.

✓ Route-Level Permissions

When a service integrates the SDK, its available routes automatically appear in the Verge Auth dashboard for permissions assignment.

✓ Group & User Management

Assign roles to users or user groups for highly flexible access control.

✓ Secure Communication

All microservice-to-auth communication is secured using service credentials provided during onboarding.

🧭 End-to-End User Flow

1. Account Creation

Users sign up with their organization details, company domain, and email.

2. Email Verification

A verification link is sent from no-reply@vergeinfosoft.com
.
Once verified, the user is redirected to the Verge Auth platform.

3. Login

Users can sign in through the “Verge IAM” login page using their verified email and password.

4. Auth Dashboard

Once logged in, the dashboard displays:

Total users

Active groups

Available roles

Audit logs

Permissions overview

🎛 Role-Based Access Control (RBAC)

RBAC inside Verge Auth is designed to be extremely intuitive — while supporting enterprise-level control.

Creating a Role

Inside the Roles section:

Click New Role

Enter the role name (e.g., HR Manager, Operations Admin)

Optional: Add a description

Select the Service you want this role to access

Example: employees-service, billing-service, appointments-service

After selecting a service, the system automatically shows all available routes for that service

Example:

/employees/

/employees/{id}

/employees/create

/employees/update

/employees/delete

Each route is presented with clear CRUD permissions:

Create

Read

Update

Delete

You can either:

Grant Full Access to that service

OR choose granular permissions route-by-route

Save the role

It instantly becomes available for assignment

Role creation modal with a dropdown for service selection and an auto-generated route list for CRUD assignment.

🧑‍🤝‍🧑 Assigning Roles to Users or Groups

After creating a role, you can:

Assign to a User

Go to Manage Users

Edit a user

Select one or more roles

Save changes

Assign to a User Group

Create a group (e.g., HR Team, Finance Department)

Assign roles to the group

Add users into the group
(they automatically inherit the group’s permissions)

This makes onboarding smoother and keeps role management scalable.

🔌 Integrating the SDK Into a Microservice
Install from PyPI
pip install verge_auth_sdk

Add the Middleware
from fastapi import FastAPI
from verge_auth_sdk import add_central_auth

app = FastAPI()
add_central_auth(app)

That’s it.
The service will now:

✓ Authenticate incoming requests
✓ Communicate securely with Verge Auth
✓ Provide user identity + roles
✓ Automatically register its routes for RBAC assignment

⚙ Environment Configuration

Each service requires a minimal set of environment variables:

######################################################################

AUTH_INTROSPECT_URL=<auth-server-introspection-endpoint>
AUTH_LOGIN_URL=<auth-server-login-ui>

VERGE_CLIENT_ID=<client-id>
VERGE_CLIENT_SECRET=<client-secret>

VERGE_SERVICE_SECRET=<service-integration-secret>

# These are provided by Verge Infosoft during onboarding.

# Optional secret provider:

SECRETS_PROVIDER=env # azure | aws

########################################################################

🛡 Middleware Responsibilities

The SDK transparently handles:

User authentication

Role injection

Cookie vs header auth

Unauthorized access responses

Service-level authentication

Route registration

You do not need to implement any auth or RBAC logic manually.

🔐 Security Highlights

RSA-based JWT verification

Centralized session & token lifecycle management

Strong encryption for service credentials

Multi-layer permission checks (Role → Service → Route → Operation)

HTTPS-only communication

Support for cloud key vaults

💼 Ideal For

HRMS, ERP, CRM, Billing platforms

Multi-tenant SaaS applications

Modern microservice architectures

Secure admin dashboards

Enterprise platforms needing consistent access control

🆘 Support & Onboarding

For enterprise onboarding, custom integrations, or troubleshooting:

🌐 Website
https://www.vergeinfosoft.com

📧 Email
contactus@vergeinfosoft.com
