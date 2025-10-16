- 2025-10-15T22:45:53Z Feature: Initial FastAPI backend scaffold with automated migrations and authentication endpoints.

- 2025-10-15T22:58:19Z Feature: Added Tactical Desk front-end experience with responsive dashboard, theming, and login/setup workflows.
- 2025-10-15T23:42:57Z Feature: Introduced deployment installers, maintenance API/UI with secure token gating, and MySQL-aware configuration fallback.
- 2025-10-15T23:54:53Z Fix: Hardened install scripts to auto-install python3 and venv prerequisites before provisioning virtual environments.
- 2025-10-16T00:08:09Z Fix: Added PYTHONPATH configuration and app directory hints to service definitions to resolve startup import failures.

- 2025-10-16T00:15:24Z Fix: Prevent update script from reinstalling requirements and restarting service when code is unchanged.
- 2025-10-16T00:19:54Z Fix: Ensure update script checks for --app-dir flag without invoking grep option parsing errors.
- 2025-10-16T00:25:00Z Fix: Added missing email-validator dependency to restore application startup.
- 2025-10-16T00:40:00Z Fix: Stabilized database initialization by reusing a shared async engine and running migrations before serving requests.
- 2025-10-16T00:46:20Z Fix: Corrected migration directory discovery so schema migrations run and user tables are created on startup.
- 2025-10-16T01:10:00Z Fix: Guarded password length and switched to native bcrypt hashing to prevent admin setup failures from bcrypt 72-byte limits.
- 2025-10-16T01:28:00Z Fix: Restored sidebar navigation with dedicated ticket, analytics, and automation workspaces and highlighted active views.
- 2025-10-16T02:10:00Z Feature: Redesigned Unified Ticket Workspace with interactive filters, sortable ticket table, and update workflow drawer.
- 2025-10-16T02:26:00Z Fix: Wired dashboard webhook admin button to maintenance view and anchored monitoring panel for direct navigation.
- 2025-10-16T02:30:00Z Fix: Resolved ticket filter rendering crash by removing unsafe loop.parent usage in templates.
