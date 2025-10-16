- 2025-10-15T22:45:53Z Feature: Initial FastAPI backend scaffold with automated migrations and authentication endpoints.

- 2025-10-15T22:58:19Z Feature: Added Tactical Desk front-end experience with responsive dashboard, theming, and login/setup workflows.
- 2025-10-15T23:42:57Z Feature: Introduced deployment installers, maintenance API/UI with secure token gating, and MySQL-aware configuration fallback.
- 2025-10-15T23:54:53Z Fix: Hardened install scripts to auto-install python3 and venv prerequisites before provisioning virtual environments.
- 2025-10-16T00:08:09Z Fix: Added PYTHONPATH configuration and app directory hints to service definitions to resolve startup import failures.

- 2025-10-16T00:15:24Z Fix: Prevent update script from reinstalling requirements and restarting service when code is unchanged.
- 2025-10-16T00:25:00Z Fix: Added missing email-validator dependency to restore application startup.
- 2025-10-16T00:40:00Z Fix: Stabilized database initialization by reusing a shared async engine and running migrations before serving requests.
