"""Default Job descriptions, one per Role of the Selection Role list.

A new Job starts with the description of its Role, so the manager edits a
correct, complete text instead of writing one from nothing. Changing the Role
of a Draft replaces the description only while it is still the previous Role's
default (or empty): text the manager wrote is never overwritten.

The texts describe the Role only. They state no pay, schedule, headcount or
location: those belong to the single Job and are entered there.
"""

from __future__ import annotations

ROLE_DESCRIPTIONS: dict[str, str] = {
    "SERVER": (
        "We are looking for a Server to look after our guests from the moment they sit down until they leave. "
        "You take orders accurately, explain the menu and the wine list, suggest dishes with confidence and make "
        "sure every table gets what it needs at the right time. Experience in full-service restaurants is preferred; "
        "we teach our menu, our wines and our service sequence."
    ),
    "FOH_SUPERVISOR": (
        "We are looking for a Front of House Team Leader to run the dining room during service. You guide and support "
        "the servers, hosts, bussers and food runners, keep the pace of service steady, handle guest requests and "
        "complaints calmly and make sure our standards are respected on every shift. Previous experience leading a "
        "team in a full-service restaurant is required."
    ),
    "BARTENDER": (
        "We are looking for a Bartender to prepare and serve cocktails, wine and other drinks for the bar and the "
        "dining room. You keep the bar clean, stocked and organized, follow our recipes precisely, serve alcohol "
        "responsibly and give bar guests the same attention as any table. Bartending experience is required."
    ),
    "HOST": (
        "We are looking for a Host to welcome our guests and give them their first impression of the restaurant. "
        "You greet guests at the door, manage reservations and the waiting list, seat tables in a balanced way for "
        "the servers and answer the phone. A friendly, organized person who stays calm when it gets busy."
    ),
    "BUSSER": (
        "We are looking for a Busser to keep the dining room clean and ready for our guests. You clear and reset "
        "tables quickly, refill water and bread, support the servers during service and help keep the floor and "
        "service stations in order. No experience is required; we teach you everything you need."
    ),
    "FOOD_RUNNER": (
        "We are looking for a Food Runner to bring dishes from the kitchen to the right table, on time and exactly "
        "as the chef plated them. You know which dish goes to which guest, check every plate before it leaves the "
        "kitchen and help the servers and bussers keep service moving. No experience is required; we teach you the menu."
    ),
    "FOH_MANAGER": (
        "We are looking for a Front of House Manager to lead the dining room, the bar and the service team. You plan "
        "shifts, train and coach the staff, look after guest satisfaction, control costs and make sure every service "
        "runs to our standards. Management experience in a full-service restaurant is required."
    ),
    "LINE_COOK": (
        "We are looking for a Line Cook to prepare our dishes during service, following our recipes and plating "
        "standards. You set up and run your station, keep it clean and organized, respect food safety rules and work "
        "closely with the rest of the kitchen to send out every order on time. Line cooking experience is required."
    ),
    "PREP_COOK": (
        "We are looking for a Prep Cook to prepare the ingredients our kitchen needs for each service. You wash, cut "
        "and portion ingredients, prepare sauces and bases following our recipes, label and store everything "
        "correctly and keep your area clean. Kitchen experience is a plus; we teach our recipes."
    ),
    "PIZZA_COOK": (
        "We are looking for a Pizza Cook to prepare our pizzas from the dough to the oven. You stretch and top each "
        "pizza following our recipes, manage the oven during service, keep your station clean and organized and "
        "make sure every pizza leaves the kitchen consistent and on time. Pizza-making experience is preferred."
    ),
    "DISHWASHER": (
        "We are looking for a Dishwasher to keep plates, glasses, pots and kitchen tools clean and ready for service. "
        "You run the dish machine, wash by hand where needed, put everything back in its place and help keep the "
        "kitchen clean and safe. No experience is required; reliability and a good pace matter most."
    ),
    "SOUS_CHEF": (
        "We are looking for a Sous Chef to support the Chef in running the kitchen and to lead it when the Chef is "
        "away. You supervise the cooks during service, check the quality of every dish, organize prep and orders and "
        "make sure food safety rules are followed. Experience as a sous chef or senior cook is required."
    ),
    "CHEF": (
        "We are looking for a Chef to lead our kitchen. You are responsible for the menu, the quality and consistency "
        "of every dish, the kitchen team, food costs, ordering and food safety. You train the cooks, keep our recipes "
        "authentic and work with the management on new dishes. Experience leading a professional kitchen is required."
    ),
    "BOH_MANAGER": (
        "We are looking for a Kitchen Manager to organize the back of house. You plan the kitchen schedule, manage "
        "ordering and inventory, control food and labor costs, make sure food safety and cleaning standards are met "
        "and support the Chef and the cooks so that every service runs smoothly. Kitchen management experience is required."
    ),
    "ASSISTANT_GENERAL_MANAGER": (
        "We are looking for an Assistant General Manager to support the General Manager in running the restaurant. "
        "You lead shifts, supervise front and back of house, handle guests, staff and daily operations and take full "
        "responsibility for the restaurant when the General Manager is away. Restaurant management experience is required."
    ),
    "GENERAL_MANAGER": (
        "We are looking for a General Manager to run the restaurant. You are responsible for the guest experience, "
        "the team, the financial results and our standards in every area of the business. You hire, train and lead "
        "the managers and staff, and work closely with the owners. Experience as a restaurant general manager is required."
    ),
}


def default_description(role_code: str | None) -> str:
    """The default description of a Role, or an empty string for a Role without one."""
    return ROLE_DESCRIPTIONS.get(role_code or "", "")


def is_default_or_empty(text: str | None) -> bool:
    """True when the text is empty or is exactly one Role's default (so it may be replaced)."""
    text = (text or "").strip()
    return not text or text in ROLE_DESCRIPTIONS.values()
