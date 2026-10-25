# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

Fortuna is Odoo 19.0 Community with project-specific customizations. `odoo/` is the unmodified upstream framework kernel; `addons/` contains the full stock Odoo addon set (`account`, `sale`, `l10n_*`, etc.) plus a handful of project-owned addons mixed into the same directory:

- **`addons/l10n_cr_fe_crlibre/`** — the main project deliverable. A PoC integration between Odoo and Hacienda's electronic-invoicing platform via the third-party **CRLibre** API (Costa Rica, FE v4.4). Generates invoice clave/XML, submits it, tracks acceptance status, and pulls the CABYS product-classification catalog and taxpayer economic-activity data from external APIs.
- **`addons/distribuidora_compras/`, `addons/distribuidora_ventas/`, `addons/distribuidora_config/`** — smaller addons customizing purchase/sale flows and menu visibility for the distributor business.

When touching any of these, treat them as the actual product code — everything else under `addons/` is vendored upstream and should generally not be modified.

## Key Commands

```bash
# Install Python dependencies
python -m pip install -r requirements.txt

# Local stack via Docker (Postgres 16 + Odoo 19 at http://localhost:8069, mounts local addons/)
docker compose up

# Start the server directly
python odoo-bin -d <database> --addons-path=addons,odoo/addons

# Initialize a database with a module
python odoo-bin -d <database> -i <module> --stop-after-init

# Upgrade the primary custom addon after changes
python odoo-bin -d <database> -u l10n_cr_fe_crlibre --stop-after-init

# Run all tests for a module
python odoo-bin -d <database> --test-enable --stop-after-init -i l10n_cr_fe_crlibre

# Run tests filtered by tag
python odoo-bin -d <database> --test-enable --test-tags <tag> --stop-after-init

# Interactive shell (with ORM access)
python odoo-bin shell -d <database>

# Lint / format
ruff check .
ruff format .
```

The CRLibre API integration expects a base URL at `ir.config_parameter` key `l10n_cr_fe.api_url` (see `addons/l10n_cr_fe_crlibre/data/system_params.xml`), defaulting to a local sandbox at `http://host.docker.internal:8080`.

## l10n_cr_fe_crlibre Architecture

- `models/fe_config.py` — `l10n_cr.fe.config`, per-company Hacienda credentials/settings (environment, identification, province/canton/district codes, economic activity).
- `models/crlibre_client.py` — HTTP client wrapping the CRLibre API (submit FE, query status, retries).
- `models/cabys_client.py` / `wizards/cabys_wizard.py` — lookup against the CABYS product-classification catalog.
- `models/partner_activity.py` / `models/partner_activity_client.py` / `wizards/partner_activity_wizard.py` — fetch and assign a partner's Hacienda-registered economic activity code, propagated onto sale orders (`models/sale_order.py`) and invoices.
- `models/account_move.py` (largest file, ~740 lines) — core invoice logic: builds the FE payload, drives the post/submit/status-check flow, and handles credit/debit note (nota de crédito/débito) and tiquete electrónico variants. Related wizards: `wizards/account_debit_note.py`, `wizards/account_move_reversal.py`, `wizards/mr_motivo_wizard.py` (motivo de anulación/reversal reason).
- `models/proveedor_email.py` / `wizards/proveedor_upload.py` — vendor-side XML reception (receiving FEs emitted by suppliers), including XML parsing and email-based acceptance.
- `migrations/19.0.1.0.1/` — Odoo-style versioned migration scripts; add new ones here (not ad hoc data fixes) when a released version needs a data/schema change.

Tests in `addons/l10n_cr_fe_crlibre/tests/` mirror this breakdown one-to-one (e.g. `test_crlibre_client.py`, `test_nota_credito_fe.py`, `test_tiquete_electronico_fe.py`, `test_recepcion_proveedores_fe.py`) — when adding a feature, add or extend the matching `test_<behavior>.py` rather than creating a new file per method.

## Coding & Commit Conventions

- Four-space indentation; `snake_case` for files/functions/variables, `PascalCase` for model and test classes, stable descriptive `snake_case` XML IDs.
- Import order enforced by `ruff.toml`: stdlib → third-party → `odoo` → `odoo.addons`.
- Register new Python modules in the addon's `__init__.py`; declare new XML/CSV/asset files in `__manifest__.py`.
- Commit subjects are Conventional Commits, usually in Spanish, scoped to the affected addon: `feat(l10n_cr_fe_crlibre): ...`, `fix(distribuidora_ventas): ...`.
- Never commit database dumps, credentials, Hacienda/CRLibre API secrets, or production config — use Odoo system parameters or local, untracked config instead.

## Odoo Framework Orientation (for `odoo/` core work)

### ORM Layer (`odoo/orm/`)

- `Model` — persistent records (`_name = 'module.model'`)
- `TransientModel` — temporary records (wizards), auto-deleted
- `AbstractModel` — mixin base, no table

Fields are class attributes from `odoo.fields` (`Char`, `Integer`, `Float`, `Boolean`, `Date`, `Datetime`, `Many2one`, `One2many`, `Many2many`, `Selection`, `Binary`, `Html`, etc.). The package is split across `models.py`, `fields.py`, `fields_relational.py`, `fields_temporal.py`, `environments.py`, `domains.py`, `registry.py`, `decorators.py`.

### HTTP Layer (`odoo/http.py`)

Controllers extend `odoo.http.Controller` and expose routes via `@http.route()`:

```
WSGI → Application.__call__ → Request._serve_static / _serve_nodb / _serve_db
     → Dispatcher.dispatch → @route decorated endpoint
```

### API Decorators (`odoo/api/`)

- `@api.model` — no recordset, class-level
- `@api.depends(...)` — computed field dependencies
- `@api.onchange(...)` — UI-only triggers
- `@api.constrains(...)` — validation

### Service Layer (`odoo/service/`)

- `server.py` — process/worker management (prefork, gevent, threading modes)
- `model.py` — XML-RPC dispatch to model methods
- `db.py` — database management (create, drop, backup)

### Test Framework (`odoo/tests/`)

- `TransactionCase` — each test gets a transaction rolled back at the end
- `SavepointCase` — savepoints for faster isolation
- `HttpCase` — full HTTP stack, browser tests via `browser_js()`

Tag tests with `@tagged(...)`; use `-at_install` / `+post_install` for timing (post-install integration tests should be `@tagged('post_install', '-at_install')`).

### Import Conventions

```python
# future → stdlib → third-party → odoo (first-party) → odoo.addons (local)
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
```
