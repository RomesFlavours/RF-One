"""«Crea in Clover» from a Registry card (REGISTRY_CLOVER_CREATE_001, Product Owner 2026-11-22).

Registry -> Clover only. For one person and one site the person is assigned to:

1. Preflight (no write, no network): the site has a Clover merchant, creation is enabled with credentials for
   that merchant, and the person has exactly one current Registry role at the site.
2. Role: the Clover API needs a role ID, so the merchant's role catalogue is read and ONLY the role whose name is
   the same as the Registry role is used. None or more than one: the card shows the error and nothing is sent;
   no other role is ever chosen. Permissions stay with Clover: RF-One sends no system level and checks none, and
   it never creates or changes roles or permissions. (No correspondence table is required.)
3. Claim: an attempt (event CLOVER_CREATE_REQUESTED) is committed before Clover is called. Only the oldest open
   attempt of a (person, site) may send; a concurrent or double-clicked request is SUPERSEDED.
4. Create in that merchant with the RF-One custom ID `RF1-<person id>`, read back the role, and save the returned
   employee ID as the site's POS ID on the same card (`employee_directory.set_pos_id`).
5. Duplicates: an uncertain answer, or a creation not saved, keeps the attempt OPEN. Every later request first
   searches Clover for the custom ID and saves what it finds. An open attempt is closed only by finding the
   employee in Clover (link recovered) - never by elapsed time, an empty search or a manual closing - so no
   second creation is sent while the first one may exist. A POS ID typed manually on the card also ends it (the
   site is then linked). Only a definite refusal by Clover (nothing created) allows a new attempt.

Clover staff data never creates or updates a card here: only the ID of the employee RF-One itself created is
stored. The manual POS ID entry stays available for employees already in Clover.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from sqlalchemy import select

from . import employee_directory as directory
from . import models as m
from .technical.connectors.clover import employee_writer

REQUESTED, DONE, REFUSED, UNCERTAIN, RECOVERED, SUPERSEDED, BLOCKED = (
    "CLOVER_CREATE_REQUESTED", "CLOVER_CREATE_DONE", "CLOVER_CREATE_REFUSED", "CLOVER_CREATE_UNCERTAIN",
    "CLOVER_CREATE_RECOVERED", "CLOVER_CREATE_SUPERSEDED", "CLOVER_CREATE_BLOCKED")
TERMINAL = {DONE, REFUSED, RECOVERED, SUPERSEDED}
ACTIONS = {REQUESTED, DONE, REFUSED, UNCERTAIN, RECOVERED, SUPERSEDED, BLOCKED}
CUSTOM_ID_PREFIX = "RF1-"


def _l(en: str, it: str) -> str:
    """Local development UI is Italian, shared/release English (UI_DEVELOPMENT_LANGUAGE_001)."""
    return it if os.environ.get("RFONE_UI_LANGUAGE") == "it" else en


def custom_id(employee_id: int) -> str:
    return f"{CUSTOM_ID_PREFIX}{employee_id}"


@dataclass
class Plan:
    employee_id: int
    restaurant_id: int
    merchant_id: str | None = None
    location_id: int | None = None
    restaurant_role_id: int | None = None
    role_name: str | None = None
    missing: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    level: str            # info | error
    message: str


def current_roles(db, employee_id, restaurant_id):
    return list(db.execute(directory._current(
        select(m.EmployeeAssignment.restaurant_role_id, m.RestaurantRole.name)
        .join(m.RestaurantRole, m.RestaurantRole.id == m.EmployeeAssignment.restaurant_role_id)
        .where(m.EmployeeAssignment.employee_id == employee_id, directory._site_condition(restaurant_id)),
        directory._now())))


def preflight(db, employee_id, restaurant_id, *, writer_available=employee_writer.availability) -> Plan:
    """Everything that can be checked without writing and without calling Clover."""
    plan = Plan(employee_id=employee_id, restaurant_id=restaurant_id)
    location = directory.site_clover_location(db, restaurant_id)
    if location is None:
        plan.missing.append(_l("This site has no Clover connection (no Clover merchant is configured for it).",
                               "La sede non ha un collegamento Clover (nessun merchant Clover configurato)."))
    else:
        plan.merchant_id, plan.location_id = location.source_location_id, location.id
        reason = writer_available(plan.merchant_id)
        if reason:
            plan.missing.append(reason)
    roles = current_roles(db, employee_id, restaurant_id)
    if not roles:
        plan.missing.append(_l("The person has no current Registry role at this site.",
                               "La persona non ha un ruolo Registry in questa sede."))
    elif len({r[0] for r in roles}) > 1:
        plan.missing.append(_l("The person has more than one current Registry role at this site.",
                               "La persona ha più di un ruolo Registry in questa sede."))
    else:
        plan.restaurant_role_id, plan.role_name = roles[0]
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
    """What the card shows for this site: the last outcome and the open attempt, if any."""
    events = _events(db, employee_id, restaurant_id)
    opened = open_attempts(db, employee_id, restaurant_id)
    last = next((e for e in reversed(events) if e.action not in (REQUESTED, SUPERSEDED)), None)
    return {"open": opened[0] if opened else None, "last": last}


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


def _record_uncertain(SessionFactory, plan, attempt_id, account_id, **details):
    with SessionFactory() as db:
        _event(db, UNCERTAIN, plan, account_id=account_id, attempt_id=attempt_id, **details)
        db.commit()


def _recover(SessionFactory, plan, attempt_id, writer, account_id) -> Outcome:
    """The only way an open attempt ends: its employee is found in Clover by the RF-One custom ID."""
    found = writer.find_by_custom_id(custom_id(plan.employee_id))
    if not found.ok:
        _record_uncertain(SessionFactory, plan, attempt_id, account_id, reason=f"Clover could not be searched: {found.error}")
        return Outcome("error", _l("The previous request to Clover is still uncertain and Clover could not be searched "
                                   "now. No new employee was sent; try again later.",
                                   "La richiesta precedente a Clover ha ancora un esito incerto e ora Clover non si può "
                                   "consultare. Non è stato inviato nessun nuovo dipendente: riprova più tardi."))
    if len(found.employee_ids) > 1:
        _record_uncertain(SessionFactory, plan, attempt_id, account_id,
                          reason="more than one Clover employee carries the RF-One custom ID", found=found.employee_ids)
        return Outcome("error", _l(f"Clover has {len(found.employee_ids)} employees with the RF-One custom ID "
                                   f"{custom_id(plan.employee_id)} ({', '.join(found.employee_ids)}). Nothing was saved: "
                                   "check them in Clover and type the right POS ID manually.",
                                   f"In Clover ci sono {len(found.employee_ids)} dipendenti con il custom ID RF-One "
                                   f"{custom_id(plan.employee_id)} ({', '.join(found.employee_ids)}). Non è stato salvato "
                                   "nulla: verificali in Clover e inserisci a mano il POS ID giusto."))
    if not found.employee_ids:
        return Outcome("error", _l("The previous request to Clover has an uncertain outcome and Clover does not show the "
                                   "employee yet. No second employee is sent while the first one may exist: check again "
                                   "later. If the person is in Clover with another custom ID, type the POS ID manually.",
                                   "La richiesta precedente a Clover ha un esito incerto e Clover non mostra ancora il "
                                   "dipendente. Nessun secondo inserimento finché il primo può esistere: ricontrolla più "
                                   "tardi. Se la persona è in Clover con un altro custom ID, inserisci il POS ID a mano."))
    clover_id = found.employee_ids[0]
    with SessionFactory() as db:
        try:
            _save(db, plan, clover_id, account_id=account_id, attempt_id=attempt_id, action=RECOVERED)
            db.commit()
        except ValueError as exc:
            db.rollback()
            _record_uncertain(SessionFactory, plan, attempt_id, account_id, reason=f"found {clover_id} but not saved: {exc}")
            return Outcome("error", _l(f"Clover employee {clover_id} was found but not saved: {exc}",
                                       f"Il dipendente Clover {clover_id} è stato trovato ma non salvato: {exc}"))
    return Outcome("info", _l(f"Link recovered: the Clover employee created earlier ({clover_id}) is now the POS ID of "
                              "this site.",
                              f"Collegamento recuperato: il dipendente Clover creato prima ({clover_id}) è ora il POS ID "
                              "di questa sede."))


def create_in_clover(SessionFactory, *, employee_id, restaurant_id, account_id,
                     writer_factory=employee_writer.get_writer,
                     writer_available=employee_writer.availability) -> Outcome:
    not_sent = _l("Not sent to Clover: ", "Non inviato a Clover: ")
    with SessionFactory() as db:
        link = directory.pos_links(db, employee_id).get(restaurant_id)
        if link is not None:
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
        return Outcome("error", not_sent + " ".join(plan.missing))
    try:
        writer = writer_factory(plan.merchant_id)
    except employee_writer.WriterNotAvailable as exc:
        return Outcome("error", not_sent + str(exc))
    if opened:                                    # recover first, never a second creation while uncertain
        return _recover(SessionFactory, plan, opened[0].id, writer, account_id)

    # The API needs a role ID: only the role with the same name as the Registry role, in this merchant.
    lookup = writer.find_roles_by_name(plan.role_name)
    reason = None
    if not lookup.ok:
        reason = _l(f"Clover could not be read to find the role «{plan.role_name}» ({lookup.error}).",
                    f"Non è stato possibile leggere Clover per trovare il ruolo «{plan.role_name}» ({lookup.error}).")
    elif not lookup.role_ids:
        reason = _l(f"No Clover role named «{plan.role_name}» exists in this merchant.",
                    f"Nel Clover di questa sede non esiste un ruolo chiamato «{plan.role_name}».")
    elif len(lookup.role_ids) > 1:
        reason = _l(f"This merchant has {len(lookup.role_ids)} Clover roles named «{plan.role_name}» "
                    f"({', '.join(lookup.role_ids)}): the role cannot be identified uniquely.",
                    f"Nel Clover di questa sede ci sono {len(lookup.role_ids)} ruoli chiamati «{plan.role_name}» "
                    f"({', '.join(lookup.role_ids)}): il ruolo non è identificabile in modo univoco.")
    if reason:
        with SessionFactory() as db:
            _event(db, BLOCKED, plan, account_id=account_id, reason=reason)
            db.commit()
        return Outcome("error", not_sent + reason)
    role_id = lookup.role_ids[0]

    with SessionFactory() as db:                  # claim, committed before Clover is called
        attempt = _event(db, REQUESTED, plan, account_id=account_id, custom_id=custom_id(employee_id),
                         clover_role_id=role_id, role_name=plan.role_name, restaurant_role_id=plan.restaurant_role_id)
        db.commit()
        attempt_id = attempt.id
    with SessionFactory() as db:
        first = open_attempts(db, employee_id, restaurant_id)
        if first and first[0].id != attempt_id:
            _event(db, SUPERSEDED, plan, account_id=account_id, attempt_id=attempt_id, by=first[0].id)
            db.commit()
            return Outcome("error", _l("Another «Crea in Clover» request for this site is already in progress: nothing "
                                       "more was sent.",
                                       "Un’altra richiesta «Crea in Clover» per questa sede è già in corso: non è stato "
                                       "inviato altro."))

    result = writer.create_employee(name=name, custom_id=custom_id(employee_id), role_id=role_id)
    if result.outcome == "REFUSED":
        with SessionFactory() as db:
            _event(db, REFUSED, plan, account_id=account_id, attempt_id=attempt_id, status_code=result.status_code,
                   reason=result.message)
            db.commit()
        return Outcome("error", _l(f"Clover refused the creation (HTTP {result.status_code}): {result.message}. No "
                                   "employee was created.",
                                   f"Clover ha rifiutato la creazione (HTTP {result.status_code}): {result.message}. "
                                   "Nessun dipendente creato."))
    if result.outcome != "CREATED":
        _record_uncertain(SessionFactory, plan, attempt_id, account_id, reason=result.message)
        return Outcome("error", _l(f"Clover's answer is uncertain ({result.message}). RF-One will look for the employee "
                                   "by its RF-One custom ID; no new creation is sent until it is found.",
                                   f"La risposta di Clover è incerta ({result.message}). RF-One cercherà il dipendente con "
                                   "il suo custom ID RF-One; nessun nuovo inserimento finché non viene trovato."))
    roles = writer.employee_role_ids(result.employee_id)
    role_confirmed = roles is not None and role_id in roles
    with SessionFactory() as db:
        try:
            _save(db, plan, result.employee_id, account_id=account_id, attempt_id=attempt_id, action=DONE,
                  extra={"role_confirmed": role_confirmed, "clover_role_id": role_id, "role_name": plan.role_name})
            db.commit()
        except ValueError as exc:
            db.rollback()
            _record_uncertain(SessionFactory, plan, attempt_id, account_id, clover_employee_id=result.employee_id,
                              reason=f"created {result.employee_id} in Clover but not saved: {exc}")
            return Outcome("error", _l(f"Clover created the employee {result.employee_id}, but RF-One could not save it: {exc}",
                                       f"Clover ha creato il dipendente {result.employee_id}, ma RF-One non ha potuto "
                                       f"salvarlo: {exc}"))
    suffix = "" if role_confirmed else _l(" Clover did not confirm the role on read-back: check it in Clover.",
                                          " Clover non ha confermato il ruolo alla rilettura: verificalo in Clover.")
    return Outcome("info", _l(f"Created in Clover with the role «{plan.role_name}»: POS ID {result.employee_id} saved for "
                              f"this site.{suffix}",
                              f"Creato in Clover con il ruolo «{plan.role_name}»: POS ID {result.employee_id} salvato per "
                              f"questa sede.{suffix}"))
