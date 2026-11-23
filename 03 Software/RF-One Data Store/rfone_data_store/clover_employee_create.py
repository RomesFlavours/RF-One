"""«Crea in Clover» from a Registry card (REGISTRY_CLOVER_CREATE_001, Product Owner 2026-11-22).

Registry -> Clover only. For one person and one site the person is assigned to:

1. Preflight (no write): the site has a Clover merchant, creation is enabled with credentials for that merchant,
   the person has a current assignment at the site, and exactly one explicit correspondence RF-One role ->
   Clover role exists for that site. The correspondence reused is the existing configuration
   `RegistryRoleMapping` (source CLOVER, current row, `original_key` = Clover role id): read here only in the
   RF-One -> Clover direction, as instructed by the Product Owner; OQ-7 still holds (a Clover role never
   determines an RF-One role and no new CLOVER correspondence is written). Before writing, Clover is read to
   check that the role exists and is at the base Employee level; otherwise nothing is sent.
2. Claim: an attempt (event CLOVER_CREATE_REQUESTED) is committed before Clover is called. Only the oldest
   open attempt of a (person, site) may send; a concurrent or double-clicked request is SUPERSEDED.
3. Create in that merchant with the RF-One custom ID `RF1-<person id>`, read back the role, and save the
   returned ID as the site's POS ID on the same card (`employee_directory.set_pos_id`).
4. Uncertain answer, or created but not saved: the attempt stays open. Every later request first searches Clover
   for the custom ID and saves what it finds; while nothing is found no second creation is sent. After a
   person has checked Clover, «Nessun dipendente in Clover» closes the attempt (only if the search still finds
   nothing and the attempt is older than CLEAR_AFTER).

Clover staff data never creates or updates a card here: only the ID of the employee RF-One itself created is
stored. The manual POS ID entry stays available for employees already in Clover.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import employee_directory as directory
from . import models as m
from .technical.connectors.clover import employee_writer

REQUESTED, DONE, REFUSED, UNCERTAIN, RECOVERED, SUPERSEDED, CLEARED, BLOCKED = (
    "CLOVER_CREATE_REQUESTED", "CLOVER_CREATE_DONE", "CLOVER_CREATE_REFUSED", "CLOVER_CREATE_UNCERTAIN",
    "CLOVER_CREATE_RECOVERED", "CLOVER_CREATE_SUPERSEDED", "CLOVER_CREATE_CLEARED", "CLOVER_CREATE_BLOCKED")
TERMINAL = {DONE, REFUSED, RECOVERED, SUPERSEDED, CLEARED}
ACTIONS = {REQUESTED, DONE, REFUSED, UNCERTAIN, RECOVERED, SUPERSEDED, CLEARED, BLOCKED}
CLEAR_AFTER = timedelta(minutes=2)
CUSTOM_ID_PREFIX = "RF1-"


def _l(en: str, it: str) -> str:
    """Local development UI is Italian, shared/release English (UI_DEVELOPMENT_LANGUAGE_001)."""
    return it if os.environ.get("RFONE_UI_LANGUAGE") == "it" else en


def custom_id(employee_id: int) -> str:
    return f"{CUSTOM_ID_PREFIX}{employee_id}"


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class Plan:
    employee_id: int
    restaurant_id: int
    merchant_id: str | None = None
    location_id: int | None = None
    restaurant_role_id: int | None = None
    role_name: str | None = None
    clover_role_id: str | None = None
    clover_role_label: str | None = None
    missing: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    level: str            # info | error
    message: str


def current_role(db, employee_id, restaurant_id):
    rows = list(db.execute(directory._current(
        select(m.EmployeeAssignment.restaurant_role_id, m.RestaurantRole.name)
        .join(m.RestaurantRole, m.RestaurantRole.id == m.EmployeeAssignment.restaurant_role_id)
        .where(m.EmployeeAssignment.employee_id == employee_id, directory._site_condition(restaurant_id)),
        directory._now())))
    return rows


def preflight(db, employee_id, restaurant_id, *, writer_available=employee_writer.availability) -> Plan:
    """Everything that can be checked without writing (and without calling Clover)."""
    plan = Plan(employee_id=employee_id, restaurant_id=restaurant_id)
    location = directory.site_clover_location(db, restaurant_id)
    if location is None:
        plan.missing.append(_l("This site has no Clover connection (no Clover merchant is configured for it).", "La sede non ha un collegamento Clover (nessun merchant Clover configurato)."))
    else:
        plan.merchant_id, plan.location_id = location.source_location_id, location.id
        reason = writer_available(plan.merchant_id)
        if reason:
            plan.missing.append(reason)
    roles = current_role(db, employee_id, restaurant_id)
    if not roles:
        plan.missing.append(_l("The person has no current role assignment at this site.", "La persona non ha un ruolo assegnato in questa sede."))
        return plan
    if len({r[0] for r in roles}) > 1:
        plan.missing.append(_l("The person has more than one current role at this site: the Clover role is ambiguous.", "La persona ha più di un ruolo in questa sede: il ruolo Clover è ambiguo."))
        return plan
    plan.restaurant_role_id, plan.role_name = roles[0]
    mappings = list(db.scalars(select(m.RegistryRoleMapping).where(
        m.RegistryRoleMapping.restaurant_id == restaurant_id, m.RegistryRoleMapping.source == "CLOVER",
        m.RegistryRoleMapping.restaurant_role_id == plan.restaurant_role_id,
        m.RegistryRoleMapping.valid_to.is_(None)).order_by(m.RegistryRoleMapping.id)))
    if not mappings:
        plan.missing.append(_l(f"No Clover role corresponds to the RF-One role «{plan.role_name}» at this site.", f"Nessun ruolo Clover corrisponde al ruolo RF-One «{plan.role_name}» in questa sede."))
    elif len(mappings) > 1:
        labels = ", ".join(sorted(f"«{x.original_label}»" for x in mappings))
        plan.missing.append(_l(f"The RF-One role «{plan.role_name}» corresponds to more than one Clover role at this site ({labels}): "
                               "the Clover role is ambiguous.",
                               f"Il ruolo RF-One «{plan.role_name}» corrisponde a più ruoli Clover in questa sede ({labels}): "
                               "il ruolo Clover è ambiguo."))
    else:
        plan.clover_role_id, plan.clover_role_label = mappings[0].original_key, mappings[0].original_label
    return plan


# --- attempts (append-only events on the card) ---------------------------------------------------------------
def _events(db, employee_id, restaurant_id):
    rows = db.scalars(select(m.EmployeeDirectoryEvent).where(
        m.EmployeeDirectoryEvent.employee_id == employee_id,
        m.EmployeeDirectoryEvent.action.in_(ACTIONS)).order_by(m.EmployeeDirectoryEvent.id))
    return [e for e in rows if (e.details or {}).get("restaurant_id") == restaurant_id]


def open_attempts(db, employee_id, restaurant_id):
    events = _events(db, employee_id, restaurant_id)
    closed = {(e.details or {}).get("attempt_id") for e in events if e.action in TERMINAL}
    return [e for e in events if e.action == REQUESTED and e.id not in closed]


def status(db, employee_id, restaurant_id):
    """What the card shows for this site: the last outcome and whether an attempt is still open."""
    events = _events(db, employee_id, restaurant_id)
    opened = open_attempts(db, employee_id, restaurant_id)
    last = next((e for e in reversed(events) if e.action not in (REQUESTED, SUPERSEDED)), None)
    return {"open": opened[0] if opened else None, "last": last,
            "can_clear": bool(opened) and _now() - _aware(opened[0].created_at) >= CLEAR_AFTER}


def _event(db, action, plan, *, account_id, **details):
    event = m.EmployeeDirectoryEvent(employee_id=plan.employee_id, account_id=account_id, action=action,
                                     details={"restaurant_id": plan.restaurant_id, "merchant_id": plan.merchant_id,
                                              **details})
    db.add(event)
    db.flush()
    return event


def _save(db, plan, clover_employee_id, *, account_id, attempt_id, action, extra=None):
    """Save the Clover ID as POS ID of the same card for this site (same rules as the manual entry)."""
    directory.set_pos_id(db, employee_id=plan.employee_id, restaurant_id=plan.restaurant_id,
                         pos_id=clover_employee_id, account_id=account_id)
    _event(db, action, plan, account_id=account_id, attempt_id=attempt_id, pos_id=clover_employee_id, **(extra or {}))


def _recover(SessionFactory, plan, attempt_id, writer, account_id) -> Outcome:
    found = writer.find_by_custom_id(custom_id(plan.employee_id))
    with SessionFactory() as db:
        if not found.ok:
            _event(db, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id,
                   reason=f"Clover could not be searched: {found.error}")
            db.commit()
            return Outcome("error", _l("The previous request to Clover is still uncertain and Clover could not be searched now. No new "
                                       "employee was sent; try again later.",
                                       "La richiesta precedente a Clover ha ancora un esito incerto e ora Clover non si può "
                                       "consultare. Non è stato inviato nessun nuovo dipendente: riprova più tardi."))
        if len(found.employee_ids) > 1:
            _event(db, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id,
                   reason="more than one Clover employee carries the RF-One custom ID", found=found.employee_ids)
            db.commit()
            return Outcome("error", _l(f"Clover has {len(found.employee_ids)} employees with the RF-One custom ID {custom_id(plan.employee_id)} "
                                       f"({', '.join(found.employee_ids)}). Nothing was saved: check them in Clover and type the "
                                       "right POS ID manually.",
                                       f"In Clover ci sono {len(found.employee_ids)} dipendenti con il custom ID RF-One "
                                       f"{custom_id(plan.employee_id)} ({', '.join(found.employee_ids)}). Non è stato salvato "
                                       "nulla: verificali in Clover e inserisci a mano il POS ID giusto."))
        if found.employee_ids:
            try:
                _save(db, plan, found.employee_ids[0], account_id=account_id, attempt_id=attempt_id, action=RECOVERED)
                db.commit()
            except ValueError as exc:
                db.rollback()
                with SessionFactory() as db2:
                    _event(db2, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id,
                           reason=f"found {found.employee_ids[0]} but not saved: {exc}")
                    db2.commit()
                return Outcome("error", _l(f"Clover employee {found.employee_ids[0]} was found but not saved: {exc}",
                                          f"Il dipendente Clover {found.employee_ids[0]} è stato trovato ma non salvato: {exc}"))
            return Outcome("info", _l(f"Link recovered: the Clover employee created earlier ({found.employee_ids[0]}) is now the POS ID of "
                                      "this site.",
                                      f"Collegamento recuperato: il dipendente Clover creato prima ({found.employee_ids[0]}) è "
                                      "ora il POS ID di questa sede."))
        db.commit()
    return Outcome("error", _l("The previous request to Clover has an uncertain outcome and Clover does not show the employee yet. "
                               "No second employee is sent while the outcome stays uncertain: check again later or verify "
                               "in Clover.",
                               "La richiesta precedente a Clover ha un esito incerto e Clover non mostra ancora il "
                               "dipendente. Nessun secondo inserimento finché l’esito resta incerto: ricontrolla più tardi "
                               "o verifica in Clover."))


def create_in_clover(SessionFactory, *, employee_id, restaurant_id, account_id,
                     writer_factory=employee_writer.get_writer,
                     writer_available=employee_writer.availability) -> Outcome:
    with SessionFactory() as db:
        if directory.pos_links(db, employee_id).get(restaurant_id) is not None:
            link = directory.pos_links(db, employee_id)[restaurant_id]
            return Outcome("info", _l(f"This site already has the POS ID {link.external_employee_id}: nothing was sent.",
                                  f"Questa sede ha già il POS ID {link.external_employee_id}: non è stato inviato nulla."))
        if restaurant_id not in directory.employee_site_ids(db, employee_id):
            return Outcome("error", _l("The person is not assigned to this site.", "La persona non è assegnata a questa sede."))
        person = db.get(m.Employee, employee_id)
        name = (person.display_name or "").strip() if person else ""
        plan = preflight(db, employee_id, restaurant_id, writer_available=writer_available)
        if not name:
            plan.missing.append(_l("The card has no name to send to Clover.", "La scheda non ha un nome da inviare a Clover."))
        opened = open_attempts(db, employee_id, restaurant_id)
    if plan.merchant_id is None or (plan.missing and not opened):
        return Outcome("error", _l("Not sent to Clover: ", "Non inviato a Clover: ") + " ".join(plan.missing))
    try:
        writer = writer_factory(plan.merchant_id)
    except employee_writer.WriterNotAvailable as exc:
        return Outcome("error", _l("Not sent to Clover: ", "Non inviato a Clover: ") + str(exc))
    if opened:                                    # recover first, never a second creation while uncertain
        return _recover(SessionFactory, plan, opened[0].id, writer, account_id)

    # Clover read before any write: the role must exist and stay at the base Employee level.
    check = writer.check_role(plan.clover_role_id)
    reason = None
    if check.error:
        reason = _l(f"Clover could not be read to check the role «{plan.clover_role_label}» ({check.error}).",
                    f"Non è stato possibile leggere Clover per verificare il ruolo «{plan.clover_role_label}» ({check.error}).")
    elif not check.found:
        reason = _l(f"The Clover role «{plan.clover_role_label}» ({plan.clover_role_id}) does not exist in this merchant.",
                    f"Il ruolo Clover «{plan.clover_role_label}» ({plan.clover_role_id}) non esiste in questo merchant.")
    elif (check.system_role or "").upper() != employee_writer.BASE_SYSTEM_ROLE:
        reason = _l(f"The Clover role «{check.name or plan.clover_role_label}» is at level {check.system_role}, above the base "
                    "Employee level: RF-One does not create employees with higher privileges.",
                    f"Il ruolo Clover «{check.name or plan.clover_role_label}» è di livello {check.system_role}, superiore "
                    "al livello base Employee: RF-One non crea dipendenti con privilegi superiori.")
    if reason:
        with SessionFactory() as db:
            _event(db, BLOCKED, plan, account_id=account_id, reason=reason)
            db.commit()
        return Outcome("error", _l("Not sent to Clover: ", "Non inviato a Clover: ") + reason)

    with SessionFactory() as db:                  # claim, committed before Clover is called
        attempt = _event(db, REQUESTED, plan, account_id=account_id, custom_id=custom_id(employee_id),
                         clover_role_id=plan.clover_role_id, clover_role_label=plan.clover_role_label,
                         restaurant_role_id=plan.restaurant_role_id)
        db.commit()
        attempt_id = attempt.id
    with SessionFactory() as db:
        first = open_attempts(db, employee_id, restaurant_id)
        if first and first[0].id != attempt_id:
            _event(db, SUPERSEDED, plan, account_id=account_id, attempt_id=attempt_id, by=first[0].id)
            db.commit()
            return Outcome("error", _l("Another «Crea in Clover» request for this site is already in progress: nothing more was sent.",
                                       "Un’altra richiesta «Crea in Clover» per questa sede è già in corso: non è stato "
                                       "inviato altro."))

    result = writer.create_employee(name=name, custom_id=custom_id(employee_id), role_id=plan.clover_role_id)
    with SessionFactory() as db:
        if result.outcome == "REFUSED":
            _event(db, REFUSED, plan, account_id=account_id, attempt_id=attempt_id, status_code=result.status_code,
                   reason=result.message)
            db.commit()
            return Outcome("error", _l(f"Clover refused the creation (HTTP {result.status_code}): {result.message}. No employee was created.",
                                       f"Clover ha rifiutato la creazione (HTTP {result.status_code}): {result.message}. "
                                       "Nessun dipendente creato."))
        if result.outcome != "CREATED":
            _event(db, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id, reason=result.message)
            db.commit()
            return Outcome("error", _l(f"Clover's answer is uncertain ({result.message}). RF-One will look for the employee by its RF-One "
                                       "custom ID before any new attempt.",
                                       f"La risposta di Clover è incerta ({result.message}). Prima di ogni nuovo tentativo "
                                       "RF-One cercherà il dipendente con il suo custom ID RF-One."))
        roles = writer.employee_role_ids(result.employee_id)
        role_confirmed = roles is not None and plan.clover_role_id in roles
        try:
            _save(db, plan, result.employee_id, account_id=account_id, attempt_id=attempt_id, action=DONE,
                  extra={"role_confirmed": role_confirmed, "clover_role_id": plan.clover_role_id})
            db.commit()
        except ValueError as exc:
            db.rollback()
            with SessionFactory() as db2:
                _event(db2, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id,
                       reason=f"created {result.employee_id} in Clover but not saved: {exc}",
                       clover_employee_id=result.employee_id)
                db2.commit()
            return Outcome("error", _l(f"Clover created the employee {result.employee_id}, but RF-One could not save it: {exc}",
                                       f"Clover ha creato il dipendente {result.employee_id}, ma RF-One non ha potuto salvarlo: {exc}"))
    suffix = "" if role_confirmed else _l(" Clover did not confirm the role on read-back: check it in Clover.",
                                           " Clover non ha confermato il ruolo alla rilettura: verificalo in Clover.")
    return Outcome("info", _l(f"Created in Clover with the role «{plan.clover_role_label}»: POS ID {result.employee_id} saved for this "
                              f"site.{suffix}",
                              f"Creato in Clover con il ruolo «{plan.clover_role_label}»: POS ID {result.employee_id} salvato "
                              f"per questa sede.{suffix}"))


def clear_attempt(SessionFactory, *, employee_id, restaurant_id, account_id,
                  writer_factory=employee_writer.get_writer) -> Outcome:
    """A person checked Clover: the open attempt created nothing. Allowed only when it is older than CLEAR_AFTER
    and the custom-ID search still finds nothing (if it finds the employee, the link is recovered instead)."""
    with SessionFactory() as db:
        opened = open_attempts(db, employee_id, restaurant_id)
        if not opened:
            return Outcome("info", _l("No open request for this site.", "Nessuna richiesta aperta per questa sede."))
        attempt = opened[0]
        if _now() - _aware(attempt.created_at) < CLEAR_AFTER:
            return Outcome("error", _l("The request is too recent: wait a couple of minutes, then check again.",
                                  "La richiesta è troppo recente: attendi un paio di minuti e ricontrolla."))
        plan = Plan(employee_id=employee_id, restaurant_id=restaurant_id,
                    merchant_id=(attempt.details or {}).get("merchant_id"))
    try:
        writer = writer_factory(plan.merchant_id)
    except employee_writer.WriterNotAvailable as exc:
        return Outcome("error", str(exc))
    found = writer.find_by_custom_id(custom_id(employee_id))
    if not found.ok or found.employee_ids:
        return _recover(SessionFactory, plan, attempt.id, writer, account_id)
    with SessionFactory() as db:
        _event(db, CLEARED, plan, account_id=account_id, attempt_id=attempt.id)
        db.commit()
    return Outcome("info", _l("Clover has no employee with the RF-One custom ID: the request is closed and a new «Crea in Clover» is "
                              "allowed.",
                              "Clover non ha dipendenti con il custom ID RF-One: la richiesta è chiusa e si può usare di "
                              "nuovo «Crea in Clover»."))
