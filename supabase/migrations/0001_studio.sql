-- Cloud AI Animation Studio - core schema
-- Documents are stored as jsonb (`data`) with a few indexed columns so the
-- Python worker (service role) and the PWA (authenticated owner) share one model.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- tables
create table if not exists public.series (
  id text primary key,
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.characters (
  id text primary key,                       -- persistent Character ID
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  series_id text references public.series(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,   -- design, voice, library, lora, reference images, hashes
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.locations (
  id text primary key,
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  series_id text references public.series(id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.episodes (
  id text primary key,
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  series_id text references public.series(id) on delete cascade,
  episode_number int,
  status text not null default 'draft',      -- draft|queued|rendering|needs_attention|failed|ready|scheduled|published
  data jsonb not null default '{}'::jsonb,   -- topic, script, continuity, pipeline progress, outputs, metadata, qc
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists episodes_series_idx on public.episodes(series_id, episode_number);

create table if not exists public.jobs (
  id text primary key default ('job_' || replace(gen_random_uuid()::text, '-', '')),
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  kind text not null,                        -- produce_episode | character_sheets
  episode_id text references public.episodes(id) on delete cascade,
  status text not null default 'queued',     -- queued|running|done|failed|cancelled
  priority int not null default 0,
  attempts int not null default 0,
  worker text,
  lease_until timestamptz,
  error text,
  estimate_usd numeric(10,4) not null default 0,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finished_at timestamptz
);
create index if not exists jobs_claim_idx on public.jobs(status, priority desc, created_at);

create table if not exists public.cost_ledger (
  id text primary key default ('cost_' || replace(gen_random_uuid()::text, '-', '')),
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  job_id text,
  data jsonb not null default '{}'::jsonb,   -- {usd, item, ts}
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.settings (
  id text primary key,                       -- 'budget', 'publishing', ...
  owner_id uuid references auth.users(id) on delete cascade default auth.uid(),
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- updated_at
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

do $$ declare t text; begin
  foreach t in array array['series','characters','locations','episodes','jobs','cost_ledger','settings'] loop
    execute format('drop trigger if exists touch_%1$s on public.%1$s', t);
    execute format('create trigger touch_%1$s before update on public.%1$s for each row execute function public.touch_updated_at()', t);
  end loop;
end $$;

-- ---------------------------------------------------------------- RLS
alter table public.series enable row level security;
alter table public.characters enable row level security;
alter table public.locations enable row level security;
alter table public.episodes enable row level security;
alter table public.jobs enable row level security;
alter table public.cost_ledger enable row level security;
alter table public.settings enable row level security;

do $$ declare t text; begin
  foreach t in array array['series','characters','locations','episodes','jobs','cost_ledger','settings'] loop
    execute format('drop policy if exists "%1$s owner all" on public.%1$s', t);
    execute format($p$create policy "%1$s owner all" on public.%1$s for all to authenticated
                     using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id)$p$, t);
  end loop;
end $$;

-- ---------------------------------------------------------------- queue functions
-- Atomically claim the next queued job (or one whose lease expired).
create or replace function public.claim_job(p_worker text, p_lease_seconds int default 900)
returns setof public.jobs language plpgsql security definer set search_path = public as $$
declare j public.jobs;
begin
  select * into j from public.jobs
   where status = 'queued' or (status = 'running' and lease_until < now())
   order by priority desc, created_at
   for update skip locked limit 1;
  if not found then return; end if;
  update public.jobs set status = 'running', worker = p_worker, attempts = attempts + 1,
         lease_until = now() + make_interval(secs => p_lease_seconds), error = null
   where id = j.id returning * into j;
  if j.episode_id is not null then
    update public.episodes set status = 'rendering' where id = j.episode_id and status <> 'ready';
  end if;
  return next j;
end $$;

create or replace function public.heartbeat_job(p_job text, p_worker text, p_lease_seconds int default 900)
returns void language sql security definer set search_path = public as $$
  update public.jobs set lease_until = now() + make_interval(secs => p_lease_seconds)
   where id = p_job and worker = p_worker and status = 'running';
$$;

create or replace function public.finish_job(p_job text, p_worker text, p_status text, p_error text default null)
returns void language sql security definer set search_path = public as $$
  update public.jobs set status = p_status, error = p_error,
         finished_at = case when p_status in ('done','failed') then now() else null end,
         lease_until = null
   where id = p_job and worker = p_worker;
$$;

revoke execute on function public.claim_job(text, int) from public, anon, authenticated;
revoke execute on function public.heartbeat_job(text, text, int) from public, anon, authenticated;
revoke execute on function public.finish_job(text, text, text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------- storage
insert into storage.buckets (id, name, public)
values ('studio', 'studio', false)
on conflict (id) do nothing;

-- No client-side storage policies: the PWA never talks to Storage directly; its server
-- (service role) issues short-lived signed URLs, and the worker uses the service role.

-- realtime for live progress in the PWA
do $$ begin
  begin alter publication supabase_realtime add table public.episodes; exception when others then null; end;
  begin alter publication supabase_realtime add table public.jobs; exception when others then null; end;
end $$;
