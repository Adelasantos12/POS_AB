# Deployment & Rollback Checklist

## Pre-deploy

- [ ] All tests pass locally: `python manage.py test boutique.tests`
- [ ] No pending uncommitted changes: `git status`
- [ ] Branch is up-to-date with remote: `git pull origin fix/pos-production-stabilization`
- [ ] Railway environment variables are set:
  - `DATABASE_URL` (PostgreSQL)
  - `SECRET_KEY`
  - `CLOUDINARY_URL` (if using logo upload)
  - `DJANGO_SETTINGS_MODULE=core.settings`

## Deploy to Railway

Railway auto-deploys on push to the tracked branch. `start.sh` runs
`python manage.py migrate` before the server starts, so migrations apply
automatically.

```bash
git push -u origin fix/pos-production-stabilization
```

Monitor logs in the Railway dashboard for:
- Migration output (no `CommandError` or `OperationalError`)
- Server startup (Gunicorn `Listening at` line)

## Post-deploy smoke checks

1. **Ticket financials** — Open any order with multiple payments. Reprint
   the PDF or ESC/POS receipt. The *Saldo Pendiente* must match the live
   balance in the Pedido detail view, not the frozen snapshot value.

2. **Novia list** — Load `/novias/`. The semáforo chips must render
   without a 500 error. Confirm page load time is reasonable (< 2 s for
   up to 100 novias).

3. **Novia detail** — Open any Novia that has at least one Pedido. Verify
   the page loads, último pago block shows, and saldo figures are correct.

4. **Dama detail** — Open a Dama with no medidas registered. Page must
   return 200.

5. **Cobro doble** — Attempt to pay an already-liquidated Pedido via the
   *Cobrar* button. The API must return a 400 with *"ya está pagado"* and
   no duplicate Ticket must be created.

6. **Admin str()** — Open Django Admin → Boutique → Pedidos. Any Pedido
   with `novia=None` must appear in the list without a 500 error.

## Rollback procedure

### Scenario A — Bad migration

Stop Railway deploy (cancel from dashboard) before traffic hits the new
revision. Then:

```bash
# Revert the bad migration on the DB (Railway Postgres shell or psql)
python manage.py migrate boutique <previous_migration_id>

# Force deploy the previous git revision
git revert HEAD --no-edit
git push origin fix/pos-production-stabilization
```

### Scenario B — Code bug (no migration change)

```bash
git revert HEAD --no-edit
git push origin fix/pos-production-stabilization
```

Railway will redeploy automatically. No DB action needed because this
stabilization commit adds no new migrations.

### Scenario C — Full rollback to last stable tag

```bash
git push origin <last_stable_sha>:fix/pos-production-stabilization --force-with-lease
```

Use `--force-with-lease` (not `--force`) to avoid overwriting concurrent
pushes. Confirm the Railway deployment log shows the correct commit SHA.

## Migrations in this stabilization

| Migration | Adds | Safe to reverse |
|-----------|------|-----------------|
| 0048_add_activo_to_producto | `Producto.activo BooleanField(default=True)` | Yes — DROP COLUMN |

No other migrations are introduced by this stabilization branch.
All financial and view fixes are pure Python; no schema changes.

## Monitoring after deploy

- Watch Railway logs for `ERROR` or `500` entries for 30 minutes post-deploy.
- Confirm no `AttributeError: 'NoneType' object has no attribute 'nombre'`
  in Pedido str() calls.
- Confirm no `ValueError: Negative indexing is not supported` in template
  rendering.
- Confirm `_get_live_financial_data` is called (check for the import path
  in any future stack traces — it lives in `boutique/services/ticket_service.py`).
