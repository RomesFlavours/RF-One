-- REGISTRY_DAILY_CHECK_001: read-only morning check of who is in Registry and how they got there.
-- Every row printed is something a person should look at. Run inside SET TRANSACTION READ ONLY.
-- employees.active is NULL for active people and false for inactive ones, so "active" means "is not false".

-- 1. Clover names confirmed in the last 24 hours with nobody signed in.
select '1 confirmed with nobody signed in' as check_name, e.display_name, ev.created_at::text as detail
from employee_directory_events ev left join employees e on e.id = ev.employee_id
where ev.action = 'LINK' and ev.account_id is null and ev.created_at > now() - interval '24 hours';

-- 2. Two active people with the same name.
select '2 same name twice' as check_name, lower(e.display_name), string_agg(e.id::text, ', ')
from employees e
where e.active is not false and e.id not in (select employee_id from employee_identity_aliases)
group by lower(e.display_name) having count(*) > 1;

-- 3. Active and still in Clover, but no open Registry company.
select '3 in Clover, no Registry company' as check_name, e.display_name, e.id::text
from employees e
where e.active is not false and e.id not in (select employee_id from employee_identity_aliases)
  and exists (select 1 from employee_clover_links l where l.employee_id = e.id and l.state = 'PRESENT')
  and not exists (select 1 from rfone_person_company_memberships pm
                  where pm.employee_id = e.id and (pm.valid_to is null or pm.valid_to > now()))
order by 2;

-- 4. In Clover at a restaurant but holding no Clover role there (a role lost by a download).
select '4 no Clover role at a restaurant' as check_name, e.display_name, l.location_id::text
from employee_clover_links l join employees e on e.id = l.employee_id
where l.state = 'PRESENT' and e.active is not false
  and not exists (select 1 from employee_source_roles esr join source_roles sr on sr.id = esr.source_role_id
                  where esr.employee_id = l.employee_id and sr.location_id = l.location_id)
order by 3, 2;

-- 5. Waiting to be confirmed, oldest first.
select '5 waiting to confirm' as check_name, l.snapshot->>'name', l.location_id::text || ' since ' || to_char(l.last_seen_at, 'YYYY-MM-DD')
from employee_clover_links l where l.employee_id is null and l.state = 'PRESENT' order by l.last_seen_at;

-- 6. Marked inactive in RF-One but still in Clover.
select '6 inactive but in Clover' as check_name, e.display_name, string_agg(l.location_id::text, ',')
from employees e join employee_clover_links l on l.employee_id = e.id and l.state = 'PRESENT'
where e.active is false and e.id not in (select employee_id from employee_identity_aliases)
group by e.id, e.display_name order by 2;
