-- ============================================================
-- 業者への指示書 — Supabase セットアップ
-- 新しいSupabaseプロジェクトを作成後、SQL Editor で全文を実行してください。
-- アプリのクラウド同期（Proプラン）が使う app_data テーブルと
-- 行レベルセキュリティ（各ユーザーが自分のデータだけ読み書き）を構築します。
-- ============================================================

-- 1) データテーブル（key/value をユーザー別に保存）
create table if not exists public.app_data (
  user_id    uuid        not null references auth.users(id) on delete cascade,
  key        text        not null,
  value      jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, key)            -- コード側の onConflict 'user_id,key' に対応
);

-- 2) 行レベルセキュリティを有効化
alter table public.app_data enable row level security;

-- 3) ポリシー：ログインユーザーは「自分の行」だけ全操作できる
drop policy if exists "own rows - select" on public.app_data;
drop policy if exists "own rows - insert" on public.app_data;
drop policy if exists "own rows - update" on public.app_data;
drop policy if exists "own rows - delete" on public.app_data;

create policy "own rows - select" on public.app_data
  for select using (auth.uid() = user_id);

create policy "own rows - insert" on public.app_data
  for insert with check (auth.uid() = user_id);

create policy "own rows - update" on public.app_data
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own rows - delete" on public.app_data
  for delete using (auth.uid() = user_id);

-- ============================================================
-- 実行後の設定（Supabaseダッシュボード）
--  Authentication > Providers > Email を有効化
--  Authentication > URL Configuration > Site URL に
--    https://gyosha-shiji.takazo0102.workers.dev を設定
--    （パスワードリセットのリンク戻り先になります）
--  ※プロジェクトは1週間完全未使用だと自動停止することがあります。
--    有料ユーザーが同期し始めれば停止しませんが、ローンチ前は時々アクセスを。
-- ============================================================
