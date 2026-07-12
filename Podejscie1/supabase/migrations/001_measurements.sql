-- Tabela pomiarów dla dashboardu (faza 2). Uruchom w Supabase SQL Editor lub przez CLI.

create table if not exists public.measurements (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  mass_kg double precision not null,
  verdict text not null check (verdict in ('thin', 'ok', 'fat'))
);

create index if not exists measurements_created_at_idx on public.measurements (created_at desc);

alter table public.measurements enable row level security;

-- MVP: otwarty zapis/odczyt dla klucza anon (dostosuj polityki przed produkcją — np. tylko zalogowani użytkownicy).
create policy "measurements_anon_insert"
  on public.measurements for insert
  to anon
  with check (true);

create policy "measurements_anon_select"
  on public.measurements for select
  to anon
  using (true);
