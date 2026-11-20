"""Static content for Training's first three pills.

Deliberately plain Python data, not a database editor and not a generic
"training engine" (spec §8 — "Definisci domande e contenuti come dati
modulari, senza costruire un motore generico di formazione"). `service.
ensure_pills_seeded()` is the only code that reads this module; it upserts
rows into `training_pills`/`training_questions` by their stable natural key
(`slug` / `(slug, kind, position)`) so re-running it (e.g. on every app
start, like migrations) is always safe and idempotent — never a duplicate
insert, never a silent overwrite of a row a trainer might one day edit by
hand (there is no such editor yet — spec §11, "Nessun editor di corsi o
domande").

Every question is grounded directly in the current `dish-data` JSON already
approved in `03 Software/Training/RF-One-Training.html` (ingredients,
description, sell phrases, the current wine-list pairings, allergens/
checks/restrictions) — see that file for the source of truth this content
must never contradict. None of these questions asserts an allergy/religious
suitability guarantee the source itself does not make; several explicitly
test that the reader knows to confirm an uncertain point with the kitchen
rather than guessing, matching the source's own repeated guidance.

`kind` is one of:
  - "self_check"  — practice questions shown with the pill's study content;
    never graded, never persisted as a result (see `models.TrainingAttempt`'s
    own docstring — there is deliberately no self-check attempt table).
  - "final_quiz"   — this pill's own graded quiz (`TrainingAttempt`).
  - "overall_quiz" — this pill's 3 questions when it contributes to a
    student's whole-path quiz (`TrainingOverallAttempt`).

Each pill has exactly 3 questions per `kind` (spec §5/§6/§7), one per
`category`: "ingredients" (ingredients/characteristics), "sales_pairing"
(sales phrasing/wine pairing) and "allergen_warning" (allergen/dietary
warnings). `correct_index` is 0-based into `options` (always exactly 3
options).
"""

from __future__ import annotations

PILL_DEFINITIONS: list[dict] = [
    {
        "slug": "caprese",
        "title": "Caprese of Buffalo Mozzarella",
        "learning_objectives": (
            "Know the Caprese's ingredients and key characteristics. Be able to suggest the dish and its "
            "current wine pairings to a guest. Recognise the allergen and dietary warnings noted for this dish."
        ),
        "content_version": 1,
    },
    {
        "slug": "carbonara",
        "title": "Fettuccine Carbonara",
        "learning_objectives": (
            "Know the Carbonara's ingredients and key characteristics. Be able to suggest the dish and its "
            "current wine pairings to a guest. Recognise the allergen and dietary warnings noted for this dish."
        ),
        "content_version": 1,
    },
    {
        "slug": "shrimp-pistachio",
        "title": "Fettuccine Shrimp & Pistacchio",
        "learning_objectives": (
            "Know the Shrimp & Pistacchio fettuccine's ingredients and key characteristics. Be able to suggest "
            "the dish and its current wine pairings to a guest. Recognise the allergen and dietary warnings "
            "noted for this dish."
        ),
        "content_version": 1,
    },
]


def _q(slug: str, kind: str, position: int, category: str, prompt: str, options: list[str],
       correct_index: int, explanation: str) -> dict:
    assert len(options) == 3
    assert 0 <= correct_index <= 2
    return {
        "slug": slug, "kind": kind, "position": position, "category": category, "version": 1,
        "prompt": prompt, "options": options, "correct_index": correct_index, "explanation": explanation,
    }


QUESTION_DEFINITIONS: list[dict] = [
    # ------------------------------------------------------------------ Caprese
    _q("caprese", "self_check", 1, "ingredients",
       "Which cheese is the centre of the Caprese of Buffalo Mozzarella?",
       ["Buffalo mozzarella", "Fresh cow's milk mozzarella", "Burrata"], 0,
       "The dish is built around imported Italian buffalo mozzarella — that's the ingredient to lead with "
       "when selling it."),
    _q("caprese", "self_check", 2, "sales_pairing",
       "Which wine pairing is on the current wine list for the Caprese?",
       ["Chianti", "Pinot Grigio — Tenuta Morer", "Prosecco"], 1,
       "Pinot Grigio — Tenuta Morer and Vermentino di Gallura — Costanera are the two pairings on the "
       "current wine list for this dish."),
    _q("caprese", "self_check", 3, "allergen_warning",
       "A guest asks if the Caprese is safe for a dairy allergy. What should you do?",
       ["Say yes, it's safe — it's just cheese and vegetables", "Say no dairy is used since it's a salad",
        "Confirm the mozzarella and any dressing with the kitchen before answering"], 2,
       "The dish contains milk (buffalo mozzarella) — always confirm ingredient/preparation details with "
       "the kitchen before answering an allergy question rather than guessing."),
    _q("caprese", "final_quiz", 1, "ingredients",
       "Besides buffalo mozzarella, which of these is a listed ingredient in the Caprese?",
       ["Arugula", "Parmesan", "Balsamic reduction"], 0,
       "Listed ingredients are buffalo mozzarella, fresh tomatoes, fresh basil, arugula and extra virgin "
       "olive oil."),
    _q("caprese", "final_quiz", 2, "sales_pairing",
       "What should you lead with when suggesting the Caprese to a guest?",
       ["The price", "The imported buffalo mozzarella", "The wine list"], 1,
       "The sales guidance is to lead with the imported buffalo mozzarella and the balance of textures."),
    _q("caprese", "final_quiz", 3, "allergen_warning",
       "Is the Caprese confirmed suitable for halal or kosher guests?",
       ["Yes, always", "No, never",
        "Suitability is not established — check ingredients, certification and preparation with the kitchen"],
       2,
       "The guide is explicit: halal/kosher suitability has not been established for this dish."),
    _q("caprese", "overall_quiz", 1, "ingredients",
       "What herb finishes the Caprese along with the olive oil?",
       ["Basil", "Mint", "Oregano"], 0,
       "Fresh basil and extra virgin olive oil finish the dish."),
    _q("caprese", "overall_quiz", 2, "sales_pairing",
       "Which guest question helps you decide whether to suggest the Caprese?",
       ["Do they enjoy a simple tomato-and-cheese combination?", "Do they want dessert first?",
        "Do they prefer well-done meat?"], 0,
       "The sell guidance suggests asking whether the guest enjoys a simple tomato-and-cheese combination."),
    _q("caprese", "overall_quiz", 3, "allergen_warning",
       "The Caprese menu photo shows a dark drizzle. What's the correct handling?",
       ["Tell the guest it's definitely a balsamic reduction", "Ignore it — it doesn't matter",
        "It is not identified in the recipe — check it with the kitchen before describing it"], 2,
       "The source notes flag the drizzle as unidentified — don't invent an ingredient that isn't confirmed."),

    # ---------------------------------------------------------------- Carbonara
    _q("carbonara", "self_check", 1, "ingredients",
       "What cut of pork is used in the Carbonara?",
       ["Pancetta", "Guanciale — cured pork jowl", "Prosciutto"], 1,
       "Guanciale (cured pork jowl) is the listed pork ingredient, not pancetta or prosciutto."),
    _q("carbonara", "self_check", 2, "sales_pairing",
       "Which wine on the current list suits a guest who prefers red with the Carbonara?",
       ["Pinot Nero — Tenuta del Morer", "Cabernet Sauvignon", "Merlot"], 0,
       "Gavi Essere — Essere is the white option; Pinot Nero — Tenuta del Morer is the red option for "
       "guests who prefer red."),
    _q("carbonara", "self_check", 3, "allergen_warning",
       "Is cream listed as an ingredient in the Carbonara recipe?",
       ["Yes, it's a cream sauce", "No — eggs and cheese are listed, with no cream listed",
        "Only on weekends"], 1,
       "The description is explicit: eggs and cheese are listed, with no cream listed."),
    _q("carbonara", "final_quiz", 1, "ingredients",
       "Which two allergens are flagged for the Carbonara?",
       ["Eggs and milk (Pecorino)", "Milk and soy", "Eggs and tree nuts"], 0,
       "Allergens listed are Eggs — sauce and Milk — Pecorino."),
    _q("carbonara", "final_quiz", 2, "sales_pairing",
       "How should you describe guanciale when selling the Carbonara?",
       ["As bacon", "As cured pork jowl", "As ham"], 1,
       "The sales phrase explains guanciale as cured pork jowl."),
    _q("carbonara", "final_quiz", 3, "allergen_warning",
       "A guest who avoids pork for religious reasons asks about the Carbonara. What's correct?",
       ["Say it's fine, just leave out the guanciale",
        "Flag the pork explicitly — halal/kosher suitability is not established",
        "Say all RF-One dishes are pork-free"], 1,
       "The guide says to flag the pork explicitly and that halal/kosher suitability is not established; "
       "removing a visible ingredient is not an approved modification."),
    _q("carbonara", "overall_quiz", 1, "ingredients",
       "What finishes the Carbonara sauce along with Pecorino and eggs?",
       ["Black pepper", "Nutmeg", "Chili flakes"], 0,
       "Black pepper is listed alongside guanciale, eggs and Pecorino."),
    _q("carbonara", "overall_quiz", 2, "sales_pairing",
       "Which guest preference should you check before recommending the Carbonara?",
       ["Whether they enjoy black pepper", "Whether they want it cold",
        "Whether they prefer dessert wine"], 0,
       "The sell guidance says to check that the guest enjoys black pepper before recommending it."),
    _q("carbonara", "overall_quiz", 3, "allergen_warning",
       "Is wheat confirmed in the Carbonara's fettuccine?",
       ["Yes, fully confirmed, no further checks needed",
        "Wheat is assumed but must be confirmed from the pasta recipe or label", "No wheat is used"], 1,
       "The checks note wheat is assumed and must still be confirmed from the recipe/label."),

    # ---------------------------------------------------------- Shrimp & Pistacchio
    _q("shrimp-pistachio", "self_check", 1, "ingredients",
       "Which nut is used in the Shrimp & Pistacchio fettuccine?",
       ["Almond", "Pistachio", "Walnut"], 1,
       "Pistachio is a core ingredient alongside shrimp."),
    _q("shrimp-pistachio", "self_check", 2, "sales_pairing",
       "Which wine on the current list is suggested for this dish?",
       ["Grillo Per Mari — Casa di Grazia", "Barolo", "Moscato"], 0,
       "Grillo Per Mari — Casa di Grazia and Vermentino di Gallura — Costanera are the two current "
       "pairings for this dish."),
    _q("shrimp-pistachio", "self_check", 3, "allergen_warning",
       "An ingredient in this dish is easy to forget when selling it but matters for allergies. Which one?",
       ["Tomato", "Anchovy", "Parsley"], 1,
       "The guide flags anchovy as easy to miss in a sales description but essential to mention for "
       "dietary needs."),
    _q("shrimp-pistachio", "final_quiz", 1, "ingredients",
       "Which three allergen categories are listed for this dish?",
       ["Shellfish, tree nuts, fish", "Dairy, gluten, soy", "Eggs, shellfish, dairy"], 0,
       "Listed allergens are Crustacean shellfish — shrimp, Tree nuts — pistachio, and Fish — anchovy."),
    _q("shrimp-pistachio", "final_quiz", 2, "sales_pairing",
       "What must you mention before recommending this dish, besides the shrimp-and-pistachio combination?",
       ["That it also includes anchovy and cooking wine", "That it is gluten-free", "That it is a small portion"],
       0,
       "The sell guidance says to mention the anchovy and cooking wine before recommending it."),
    _q("shrimp-pistachio", "final_quiz", 3, "allergen_warning",
       "A guest asks if this dish is alcohol-free since the wine is “cooked off”. What's correct?",
       ["Yes, cooking removes all alcohol",
        "Cooking wine must not be described as alcohol-free after cooking",
        "Only if it's simmered for over an hour"], 1,
       "The restrictions note explicitly warns against describing cooking wine as alcohol-free after cooking."),
    _q("shrimp-pistachio", "overall_quiz", 1, "ingredients",
       "Besides shrimp and pistachio, which herb is listed in the recipe?",
       ["Parsley", "Rosemary", "Thyme"], 0,
       "Garlic, parsley and anchovy add savoury depth alongside shrimp and pistachio."),
    _q("shrimp-pistachio", "overall_quiz", 2, "sales_pairing",
       "Who should you suggest this dish to?",
       ["Guests who enjoy seafood and want a more distinctive pasta", "Guests who dislike seafood",
        "Guests who want the mildest dish on the menu"], 0,
       "The sell guidance targets guests who enjoy seafood and want something distinctive."),
    _q("shrimp-pistachio", "overall_quiz", 3, "allergen_warning",
       "A guest says they just want the shrimp removed to avoid a shellfish allergy. What's correct?",
       ["That's fine, it becomes shellfish-free",
        "Removing the shrimp alone does not resolve the other allergens or cross-contact — confirm with "
        "the kitchen",
        "Only the pistachio needs to be removed"], 1,
       "The checks note explicitly: simply removing shrimp or a garnish does not resolve the other "
       "ingredients or cross-contact."),
]
