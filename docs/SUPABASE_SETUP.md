# Supabase setup for the Operations Database

The backend (`server/`) stores hazard occurrences in **Supabase Postgres** when
the right environment variables are set, and falls back to a local JSON file
otherwise. The API contract and the frontend are identical either way.

## 1. Create the project
1. Go to <https://supabase.com>, create a project, and wait for it to provision.
2. In **Project Settings -> API**, copy:
   - **Project URL** (e.g. `https://abcdxyz.supabase.co`)
   - **service_role key** (under "Project API keys"). This is a secret — it stays
     server-side and is never sent to the browser.

## 2. Create the table
Open **SQL Editor** in Supabase and run:

```sql
create table if not exists occurrences (
  id                  text primary key,
  type                text not null default 'other',
  description         text default '',
  severity            int default 3,
  score               numeric default 0,
  confidence          numeric,
  road_name           text,
  road_context        text,
  frame               text,
  image_url           text,
  lat                 double precision,
  lng                 double precision,
  justification       jsonb default '[]'::jsonb,
  priority_multiplier numeric,
  times_seen          int default 1,
  source              text default 'detection',
  status              text default 'open',
  created_at          timestamptz default now()
);

-- The backend uses the service_role key, which bypasses RLS. These policies
-- only matter if you later call Supabase directly from the browser.
alter table occurrences enable row level security;
create policy "allow all (demo)" on occurrences
  for all using (true) with check (true);
```

> For real multi-user government access, replace the permissive policy with
> Supabase Auth + per-role policies.

## 3. Configure the backend
Add to your project-root `.env`:

```bash
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key>
# optional, defaults to "occurrences"
# SUPABASE_TABLE=occurrences
```

## 4. Start the backend and seed
```bash
uvicorn server.app:app --reload --port 8000
```

- Verify the backend picked Supabase: `curl localhost:8000/api/health`
  should return `{"status":"ok","backend":"supabase"}`.
- Populate the table from the latest detection output by clicking **Reseed** in
  the Operations DB tab, or:
  ```bash
  curl -X POST localhost:8000/api/reseed
  ```

That's it — add/remove/edit in the UI now reads and writes Supabase Postgres.
Unset the `SUPABASE_*` vars to return to the local JSON store.
