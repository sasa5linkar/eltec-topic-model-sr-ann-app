-- RLS policies for the ELTeC Topic Annotation MVP.
--
-- Apply this in the Supabase SQL editor after creating the tables.
-- These policies are intentionally narrow:
-- - authenticated users can read their own profile
-- - annotators can only see their assigned work and their own annotations
-- - authenticated users can read themes
--
-- Admin operations in this app already run through the Streamlit backend with the
-- service-role key, which bypasses RLS. Because of that, this script does not grant
-- blanket browser-side "admin can do everything" access.

begin;

alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.themes enable row level security;
alter table public.segments enable row level security;
alter table public.assignments enable row level security;
alter table public.annotations enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
on public.profiles
for select
to authenticated
using (auth.uid() = id);

drop policy if exists themes_select_authenticated on public.themes;
create policy themes_select_authenticated
on public.themes
for select
to authenticated
using (true);

drop policy if exists assignments_select_own on public.assignments;
create policy assignments_select_own
on public.assignments
for select
to authenticated
using (annotator_id = auth.uid());

drop policy if exists assignments_update_own on public.assignments;
create policy assignments_update_own
on public.assignments
for update
to authenticated
using (annotator_id = auth.uid())
with check (annotator_id = auth.uid());

drop policy if exists segments_select_assigned on public.segments;
create policy segments_select_assigned
on public.segments
for select
to authenticated
using (
    exists (
        select 1
        from public.assignments a
        where a.segment_id = segments.id
          and a.annotator_id = auth.uid()
    )
);

drop policy if exists documents_select_assigned on public.documents;
create policy documents_select_assigned
on public.documents
for select
to authenticated
using (
    exists (
        select 1
        from public.segments s
        join public.assignments a on a.segment_id = s.id
        where s.document_id = documents.id
          and a.annotator_id = auth.uid()
    )
);

drop policy if exists annotations_select_own_assigned on public.annotations;
create policy annotations_select_own_assigned
on public.annotations
for select
to authenticated
using (
    annotations.annotator_id = auth.uid()
    and exists (
        select 1
        from public.assignments a
        where a.segment_id = annotations.segment_id
          and a.annotator_id = auth.uid()
    )
);

drop policy if exists annotations_insert_own_assigned on public.annotations;
create policy annotations_insert_own_assigned
on public.annotations
for insert
to authenticated
with check (
    annotations.annotator_id = auth.uid()
    and exists (
        select 1
        from public.assignments a
        where a.segment_id = annotations.segment_id
          and a.annotator_id = auth.uid()
    )
);

drop policy if exists annotations_update_own_assigned on public.annotations;
create policy annotations_update_own_assigned
on public.annotations
for update
to authenticated
using (
    annotations.annotator_id = auth.uid()
    and exists (
        select 1
        from public.assignments a
        where a.segment_id = annotations.segment_id
          and a.annotator_id = auth.uid()
    )
)
with check (
    annotations.annotator_id = auth.uid()
    and exists (
        select 1
        from public.assignments a
        where a.segment_id = annotations.segment_id
          and a.annotator_id = auth.uid()
    )
);

drop policy if exists annotations_delete_own_assigned on public.annotations;
create policy annotations_delete_own_assigned
on public.annotations
for delete
to authenticated
using (
    annotations.annotator_id = auth.uid()
    and exists (
        select 1
        from public.assignments a
        where a.segment_id = annotations.segment_id
          and a.annotator_id = auth.uid()
    )
);

commit;
