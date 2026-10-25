# Repository Guidelines

## Project Structure & Module Organization

Fortuna is based on Odoo Community 19. Core framework code lives in `odoo/`; standard and project addons live in `addons/`. Each addon is a Python package with `__manifest__.py` and `__init__.py`, typically organized into `models/`, `wizards/`, `views/`, `data/`, `security/`, and `tests/`. The main project-specific integration is `addons/l10n_cr_fe_crlibre/`. Packaging and platform files are under `setup/` and `debian/`; contributor documentation is under `doc/` and `docs/`.

## Build, Test, and Development Commands

- `python -m pip install -r requirements.txt` installs Python dependencies (Python 3.10+ and PostgreSQL 13+ are required).
- `docker compose up` starts PostgreSQL 16 and Odoo 19 at `http://localhost:8069`, mounting local `addons/`.
- `python odoo-bin -d <db> --addons-path=addons,odoo/addons` runs the checked-out server directly.
- `python odoo-bin -d <db> -u l10n_cr_fe_crlibre --stop-after-init` upgrades the primary custom addon after changes.
- `ruff check .` runs configured lint checks; `ruff format .` formats Python sources.

## Coding Style & Naming Conventions

Use four-space indentation for Python and follow existing Odoo patterns. Name files, functions, and variables in `snake_case`; models and test classes use `PascalCase`; XML IDs should be stable, descriptive `snake_case`. Keep imports grouped as standard library, third-party, `odoo`, then `odoo.addons`; `ruff.toml` enforces this order. Register new Python modules in the appropriate `__init__.py` and declare XML, CSV, and asset files in `__manifest__.py`.

## Testing Guidelines

Place addon tests in `<addon>/tests/test_<behavior>.py` and import them from `tests/__init__.py`. Use Odoo's `TransactionCase` or `HttpCase`, with methods named `test_<expected_behavior>`. Run a module suite with:

`python odoo-bin -d <db> --test-enable --stop-after-init -i l10n_cr_fe_crlibre`

For focused runs, add `--test-tags <tag>`. Tag post-install integration tests with `@tagged('post_install', '-at_install')`. No fixed coverage threshold is configured; add regression tests for every behavior change.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit subjects, usually in Spanish: `feat(l10n_cr_fe_crlibre): ...`, `fix(scope): ...`, or `docs: ...`. Keep commits focused and use the affected addon as the scope. Pull requests must complete the repository template: describe the issue or feature, current behavior, and desired behavior. Link relevant issues, note database or migration effects, list validation commands, and include screenshots for UI/view changes. Confirm the CLA and Odoo contribution guidelines before submission.

## Security & Configuration

Never commit database dumps, credentials, Hacienda/API secrets, or production configuration. Store environment-specific values in Odoo system parameters or local configuration, and review access-control CSV/XML whenever adding models or actions.
