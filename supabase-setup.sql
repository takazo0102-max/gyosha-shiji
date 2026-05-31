-- TaskFlow: Supabase テーブル作成SQL
-- Supabase Dashboard > SQL Editor で実行してください

-- ユーザーごとのタスクデータ（一括JSON保存方式）
-- シンプルさを優先: tasks/categories/recurring を1行のJSONとして保存
create table if not exists taskflow_data (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null unique,
  tasks jsonb default '[]'::jsonb,
  categories jsonb default '[]'::jsonb,
  recurring jsonb default '[]'::jsonb,
  settings jsonb default '{}'::jsonb,
  updated_at timestamptz default now(),
  created_at timestamptz default now()
);

-- RLS (Row Level Security) を有効化
alter table taskflow_data enable row level security;

-- ポリシー: ユーザーは自分のデータのみ読み書き可能
create policy "Users can read own data"
  on taskflow_data for select
  using (auth.uid() = user_id);

create policy "Users can insert own data"
  on taskflow_data for insert
  with check (auth.uid() = user_id);

create policy "Users can update own data"
  on taskflow_data for update
  using (auth.uid() = user_id);

create policy "Users can delete own data"
  on taskflow_data for delete
  using (auth.uid() = user_id);

-- updated_at を自動更新するトリガー
create or replace function update_taskflow_timestamp()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger taskflow_data_updated
  before update on taskflow_data
  for each row execute function update_taskflow_timestamp();
