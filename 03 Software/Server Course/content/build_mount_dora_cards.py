"""Builds mount_dora_dish_cards.md: draft dish cards for the Mount Dora menu.

Source of truth is the Mount Dora menu received 27 October 2026 (mount_dora_menu.md):
only the ingredients it lists are used. Where Winter Park has a card for a related
dish, the card says so and what to check, and reuses the Winter Park wording only
when the ingredients agree. Every allergen line is to confirm with the kitchen.
Replace these drafts with the kitchen's approved recipes when they exist.

Run: python content/build_mount_dora_cards.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Section notes that apply to every dish in the section (to confirm, like the rest).
SECTION = {
    "Antipasti": "",
    "Zuppe e Insalate": "",
    "Pasta Fresca": "All pasta is made fresh in-house daily: fresh pasta usually contains eggs and wheat.",
    "Pizza Gourmet": "Naturally leavened dough with imported Italian flour: wheat.",
    "Secondi": "",
    "Contorni": "",
}

# name, section, signature, ingredients (from the menu), how to present it, one phrase, Winter Park relation
D = [
    ("House Focaccia", "Antipasti", False, "Warm focaccia; extra-virgin olive oil; sea salt",
     "A simple starter to share while guests decide. Offer it warm, with the olive oil.",
     "Our focaccia comes out warm, with extra-virgin olive oil and sea salt: perfect to share while you look at the menu.",
     ("Garnished Focaccia", "Winter Park's focaccia is garnished with prosciutto; the Mount Dora menu lists it plain.")),
    ("Prosciutto e Melone", "Antipasti", False, "Parma prosciutto; ripe melon; aged balsamic",
     "A light, sweet-and-salty starter. Good for guests who want something fresh before pasta.",
     "Parma prosciutto with ripe melon and a touch of aged balsamic: sweet, salty and light.",
     ("Prosciutto and Cantaloupe", "The Mount Dora menu adds aged balsamic.")),
    ("Polpette al Sugo", "Antipasti", False, "House-made beef and pork meatballs; tomato sauce; Parmigiano; grilled bread",
     "A hearty starter to share. Mention that the meatballs are made in-house.",
     "Our meatballs are made in-house with beef and pork, in tomato sauce with Parmigiano and grilled bread.",
     ("Homemade Meatballs", "Winter Park's meatball recipe includes pesto (pine nuts and cheese). Check whether Mount Dora's does before answering a nut question.")),
    ("Arancini", "Antipasti", False, "Crisp risotto croquettes; mozzarella; basil tomato sauce",
     "A crowd-pleasing starter to share. Describe them as crisp outside, creamy risotto and mozzarella inside.",
     "Arancini are crisp risotto croquettes with mozzarella inside, served with a basil tomato sauce.",
     None),
    ("Calamari alla Griglia", "Antipasti", False, "Grilled calamari; lemon; garlic; parsley; chili",
     "For guests who like seafood and want something lighter than fried. Mention the chili.",
     "Our calamari are grilled, not fried, with lemon, garlic, parsley and a little chili.",
     None),
    ("Antipasto Italiano", "Antipasti", False, "Selection of Italian cured meats; cheeses; olives; roasted vegetables; focaccia",
     "Best for a table to share. Ask about pork and dairy before suggesting it to a guest with restrictions.",
     "The Antipasto Italiano is a selection of Italian cured meats and cheeses with olives, roasted vegetables and focaccia: made for sharing.",
     ("Tuscany Cutting Board", "Winter Park's board lists prosciutto, speck and soppressata. The Mount Dora menu says only 'Italian cured meats': ask the kitchen which ones.")),
    ("Bruschetta Trio", "Antipasti", False, "Tomato and basil; whipped ricotta and roasted peppers; goat cheese and caramelized onion; bread",
     "Three bruschette in one plate: good for guests who can't choose, or for a table to share.",
     "The Bruschetta Trio gives you three: tomato and basil, whipped ricotta with roasted peppers, and goat cheese with caramelized onion.",
     ("Tomato Bruschetta, Ricotta & Red Pepper, Goat Cheese and Sun-dried Tomato", "Winter Park's goat cheese bruschetta uses sun-dried tomato; Mount Dora's uses caramelized onion.")),
    ("Crema di Pomodoro", "Zuppe e Insalate", False, "Creamy tomato and basil soup; bread",
     "A comforting starter. Ask whether 'creamy' means cream in Mount Dora's recipe before answering a dairy question.",
     "Our Crema di Pomodoro is a creamy tomato and basil soup, served with bread.",
     ("Velvet Tomato Soup", "Check whether the recipe is the same as Winter Park's Velvet Tomato Soup.")),
    ("Zuppa del Giorno", "Zuppe e Insalate", False, "Chef's daily seasonal soup",
     "Ask the kitchen before every service what today's soup is and what's in it. Never guess.",
     "Today's soup is ... (ask the kitchen at the start of the shift).",
     None),
    ("Insalata Verde", "Zuppe e Insalate", False, "Mixed greens; cucumber; fennel; lemon vinaigrette",
     "A light salad, a good starter or side for guests who want something fresh.",
     "The Insalata Verde is mixed greens with cucumber and fennel in a lemon vinaigrette: light and fresh.",
     None),
    ("Vegetable Garden Salad", "Zuppe e Insalate", False, "Mixed greens; tomatoes; olives; roasted peppers; artichokes; red onion; red wine vinaigrette",
     "A full vegetable salad. You can suggest adding grilled chicken, salmon, shrimp or buffalo mozzarella.",
     "Our Vegetable Garden Salad has mixed greens, tomatoes, olives, roasted peppers, artichokes and red onion, with a red wine vinaigrette.",
     ("Vegetable Garden Salad", "Same name as at Winter Park. Check the ingredients match.")),
    ("Burrata Salad", "Zuppe e Insalate", False, "Burrata; arugula; tomatoes; basil; olive oil",
     "For guests who love fresh cheese. Describe burrata as mozzarella with a soft, creamy centre.",
     "The Burrata Salad has creamy burrata with arugula, tomatoes, basil and olive oil.",
     None),
    ("Tagliolini alla Carbonara", "Pasta Fresca", True, "Fresh tagliolini; egg yolk; guanciale; Pecorino Romano; black pepper",
     "A signature dish. Explain guanciale as cured pork jowl, and that the sauce is egg yolk and Pecorino, with no cream listed.",
     "Our Carbonara is a signature: fresh tagliolini with guanciale, egg yolk, Pecorino Romano and black pepper.",
     ("Fettuccine Carbonara", "Winter Park serves it with fettuccine; Mount Dora with tagliolini and egg yolk.")),
    ("Fettuccine alla Bolognese", "Pasta Fresca", True, "Fresh fettuccine; slow-cooked beef and pork ragu",
     "A signature dish. Mention the slow-cooked ragu and that it has both beef and pork.",
     "Our Bolognese is a signature: fresh fettuccine with a slow-cooked beef and pork ragu.",
     ("Fettuccine Bolognese", "Winter Park's Bolognese uses red wine: check Mount Dora's recipe.")),
    ("Tagliolini Cacio e Pepe", "Pasta Fresca", False, "Fresh tagliolini; Pecorino Romano; black pepper",
     "A Roman classic with only cheese and pepper. Good for guests who like simple, rich pasta.",
     "Cacio e Pepe is a Roman classic: fresh tagliolini with Pecorino Romano and black pepper, nothing else.",
     ("Cacio e Pepe", "Check whether Winter Park and Mount Dora use the same pasta.")),
    ("Fettuccine Gamberi e Pistacchio", "Pasta Fresca", True, "Fresh fettuccine; shrimp; pistachio; garlic; parsley; white wine; olive oil",
     "A signature dish. Always mention both the shrimp and the pistachio: they are two of the most serious allergies.",
     "Our Shrimp and Pistachio fettuccine is a signature, with garlic, parsley and a touch of white wine.",
     ("Fettuccine Shrimp & Pistacchio", "Winter Park's version also lists anchovy and tomato. The Mount Dora menu doesn't: ask the kitchen.")),
    ("Gnocchi alla Sorrentina", "Pasta Fresca", False, "House-made gnocchi; tomato sauce; melted mozzarella; basil",
     "Comforting and cheesy. Mention the gnocchi are made in-house.",
     "Our gnocchi are house-made, Sorrento-style, with tomato sauce, melted mozzarella and basil.",
     ("Homemade Gnocchi Sorrento", "At Winter Park the gnocchi contain flour (not gluten free) and the dish uses white wine: check Mount Dora's recipe.")),
    ("Gnocchi al Pesto", "Pasta Fresca", False, "House-made gnocchi; basil pesto; Parmigiano",
     "Fresh and herby. Pesto usually contains pine nuts and cheese: check before any nut or dairy question.",
     "House-made gnocchi with basil pesto and Parmigiano.",
     ("Homemade Gnocchi in Basil Pesto", "At Winter Park the pesto is made ahead, so nothing can be taken out: check whether that's the same here.")),
    ("Tagliolini al Pomodoro", "Pasta Fresca", False, "Fresh tagliolini; Italian plum tomato sauce; garlic; basil; olive oil",
     "A simple tomato pasta, good for guests who want something light or vegetarian.",
     "Fresh tagliolini with Italian plum tomato sauce, garlic, basil and olive oil.",
     ("Tagliolini alla Napoletana", "Check whether it's the same as Winter Park's Napoletana.")),
    ("Linguine alle Vongole", "Pasta Fresca", False, "Linguine; clams; garlic; white wine; parsley; chili",
     "For seafood lovers. Mention the clams and the touch of chili.",
     "Linguine with clams, garlic, white wine, parsley and a little chili.",
     None),
    ("Fettuccine Alfredo", "Pasta Fresca", False, "Fresh fettuccine; Parmigiano cream sauce",
     "Rich and creamy, popular with children and guests who want something simple.",
     "Fresh fettuccine in a Parmigiano cream sauce.",
     ("Fettuccine Alfredo", "Winter Park's Alfredo uses white wine: check Mount Dora's recipe.")),
    ("Via Napoli (Margherita)", "Pizza Gourmet", False, "Tomato; mozzarella; basil",
     "The classic. A safe choice for guests who want a simple pizza.",
     "The Via Napoli is our Margherita: tomato, mozzarella and basil.",
     ("Via Napoli", "Same pizza as at Winter Park.")),
    ("Mercati Traianei", "Pizza Gourmet", False, "Amatriciana sauce; mozzarella; red onion; guanciale; Grana Padano",
     "Bold and savoury, with guanciale (cured pork jowl).",
     "Mercati Traianei has Amatriciana sauce, mozzarella, red onion, guanciale and Grana Padano.",
     ("Mercati Traianei", "Same name as at Winter Park. Check the ingredients match.")),
    ("Testaccio", "Pizza Gourmet", False, "Tomato; mozzarella; Calabrian chili; spicy oil",
     "For guests who like it hot. Always say it's spicy.",
     "The Testaccio is a spicy one: tomato, mozzarella, Calabrian chili and spicy oil.",
     ("Testaccio", "Same name as at Winter Park. Check the ingredients match.")),
    ("Piazza di Spagna", "Pizza Gourmet", False, "Tomato; mozzarella; red peppers; black olives",
     "A vegetarian pizza with peppers and olives.",
     "Piazza di Spagna has tomato, mozzarella, red peppers and black olives.",
     ("Piazza di Spagna", "Same name as at Winter Park. Check the ingredients match.")),
    ("Trinita dei Monti", "Pizza Gourmet", False, "Tomato; mozzarella; zucchini; eggplant; red peppers; basil",
     "A vegetable pizza, a good suggestion for vegetarians.",
     "Trinità dei Monti is a vegetable pizza: zucchini, eggplant and red peppers with tomato, mozzarella and basil.",
     ("Trinità dei Monti", "Same name as at Winter Park. Check the ingredients match.")),
    ("Rome's Flavours", "Pizza Gourmet", True, "Tomato; mozzarella; Italian sausage; broccoli; Grana Padano",
     "Our signature pizza. Mention the sausage and broccoli combination.",
     "Our signature pizza, the Rome's Flavours: tomato, mozzarella, Italian sausage, broccoli and Grana Padano.",
     ("Rome's Flavours Pizza", "Check the ingredients match Winter Park's.")),
    ("Sicilia", "Pizza Gourmet", False, "Tomato; mozzarella; eggplant; ricotta salata",
     "A vegetarian pizza with eggplant and salted ricotta, inspired by Sicily.",
     "The Sicilia has tomato, mozzarella, eggplant and ricotta salata.",
     ("Via Sicilia", "Check the ingredients match Winter Park's Via Sicilia.")),
    ("Villa Borghese", "Pizza Gourmet", False, "Tomato; mozzarella; sausage; mushrooms; white truffle oil",
     "Rich and earthy, with sausage, mushrooms and truffle oil.",
     "Villa Borghese has tomato, mozzarella, sausage, mushrooms and white truffle oil.",
     ("Villa Borghese", "Same name as at Winter Park. Check the ingredients match.")),
    ("Colosseo", "Pizza Gourmet", False, "Tomato; mozzarella; spicy salami; gorgonzola; red peppers",
     "Spicy and bold, with gorgonzola. Say it's spicy.",
     "The Colosseo has tomato, mozzarella, spicy salami, gorgonzola and red peppers.",
     ("Colosseo", "Same name as at Winter Park. Check the ingredients match.")),
    ("Prosciutto e Rucola", "Pizza Gourmet", False, "Tomato; mozzarella; Parma prosciutto; arugula; shaved Parmigiano",
     "A classic: Parma prosciutto and fresh arugula on top.",
     "Prosciutto e Rucola has tomato and mozzarella, topped with Parma prosciutto, arugula and shaved Parmigiano.",
     None),
    ("White Dolomiti", "Pizza Gourmet", False, "Mozzarella; porcini mushrooms; speck; white truffle oil",
     "A white pizza (no tomato) with porcini, speck and truffle oil.",
     "The White Dolomiti is a white pizza with mozzarella, porcini mushrooms, speck and white truffle oil.",
     ("Dolomiti", "Speck is pork. Check whether it's the same as Winter Park's Dolomiti.")),
    ("Branzino al Forno", "Secondi", True, "Whole roasted branzino; lemon; garlic; fresh herbs",
     "A signature main. It's a whole fish and takes time: mention it when guests are in a hurry.",
     "Our Branzino al Forno is a signature: a whole roasted branzino with lemon, garlic and fresh herbs.",
     ("Branzino Oven Baked", "At Winter Park the whole branzino takes about 25 minutes: ask the kitchen for Mount Dora's time.")),
    ("Salmone Arrosto", "Secondi", False, "Roasted salmon; seasonal vegetables; lemon herb sauce",
     "A lighter main. Ask the kitchen what the seasonal vegetables are today.",
     "Roasted salmon with seasonal vegetables and a lemon herb sauce.",
     ("Fresh Salmon Filet", "Check the sauce against Winter Park's salmon.")),
    ("Pollo alla Puttanesca", "Secondi", False, "Chicken breast; taggiasche olives; capers; cherry tomatoes",
     "A savoury chicken main with olives and capers.",
     "Chicken breast alla Puttanesca, with taggiasche olives, capers and cherry tomatoes.",
     ("Chicken Olive and Capers", "Classic puttanesca often has anchovy: ask the kitchen before any fish allergy question.")),
    ("Tagliata di Manzo", "Secondi", False, "Sliced grilled steak; arugula; cherry tomatoes; Parmigiano; balsamic",
     "For steak lovers. Ask how they'd like it cooked.",
     "The Tagliata is sliced grilled steak on arugula with cherry tomatoes, Parmigiano and balsamic.",
     None),
    ("Brasato di Manzo", "Secondi", False, "Red wine braised short rib; creamy polenta",
     "A rich, slow-cooked main for cooler evenings. It's braised in red wine.",
     "The Brasato is short rib braised in red wine, served on creamy polenta.",
     None),
    ("Costolette d'Agnello alle Erbe", "Secondi", False, "Herb-seared lamb chops; roasted potatoes",
     "For guests who like lamb. Ask how they'd like it cooked.",
     "Herb-seared lamb chops with roasted potatoes.",
     ("Herbs Lamb", "Check whether it's the same as Winter Park's lamb.")),
    ("Melanzane alla Parmigiana", "Secondi", False, "Baked eggplant; tomato sauce; mozzarella; basil",
     "A vegetarian main. Ask the kitchen whether the eggplant is fried or breaded first.",
     "Melanzane alla Parmigiana: baked eggplant layered with tomato sauce, mozzarella and basil.",
     None),
    ("Rosemary Roasted Potatoes", "Contorni", False, "Potatoes; rosemary", "A side for any main.",
     "Roasted potatoes with rosemary.", None),
    ("Broccolini Aglio e Olio", "Contorni", False, "Broccolini; garlic; olive oil", "A side for any main.",
     "Broccolini with garlic and olive oil.", None),
    ("Sauteed Spinach", "Contorni", False, "Spinach", "A side for any main.", "Sautéed spinach.", None),
    ("Seasonal Roasted Vegetables", "Contorni", False, "Seasonal vegetables",
     "A side for any main. Ask the kitchen what's in it today.", "Today's roasted vegetables are ... (ask the kitchen).",
     ("Vegetable Festival", "Check whether it's like Winter Park's Vegetable Festival side.")),
    ("Creamy Parmigiano Polenta", "Contorni", False, "Polenta; Parmigiano", "A side for any main.",
     "Creamy polenta with Parmigiano.", None),
]

ALLERGENS = [  # (word in the ingredients, allergen note)
    ("mozzarella", "Milk: mozzarella"), ("burrata", "Milk: burrata"), ("ricotta", "Milk: ricotta"),
    ("goat cheese", "Milk: goat cheese"), ("parmigiano", "Milk: Parmigiano"), ("pecorino", "Milk: Pecorino"),
    ("grana", "Milk: Grana Padano"), ("gorgonzola", "Milk: gorgonzola"), ("cheeses", "Milk: cheeses"),
    ("cream", "Milk: cream"), ("egg yolk", "Eggs: egg yolk"), ("pistachio", "Tree nuts: pistachio"),
    ("pesto", "Tree nuts: pesto usually has pine nuts"), ("shrimp", "Crustaceans: shrimp"),
    ("clams", "Molluscs: clams"), ("calamari", "Molluscs: calamari"), ("salmon", "Fish: salmon"),
    ("branzino", "Fish: branzino"), ("focaccia", "Wheat: focaccia"), ("bread", "Wheat: bread"),
    ("croquettes", "Wheat and possibly eggs: croquette coating"), ("gnocchi", "Wheat: gnocchi usually contain flour"),
    ("linguine", "Wheat: linguine"),
]
PORK = ("guanciale", "pork", "prosciutto", "sausage", "speck", "salami", "cured meats")
ALCOHOL = ("white wine", "red wine")


def card(name, section, sig, ingredients, present, phrase, wp):
    low = ingredients.lower()
    notes = [n for w, n in ALLERGENS if w in low]
    if SECTION[section] and section in ("Pasta Fresca", "Pizza Gourmet") and not name.startswith("Gnocchi"):
        notes.append("Wheat" + (" and eggs: fresh pasta" if section == "Pasta Fresca" else ": pizza dough"))
    diet = []
    if any(p in low for p in PORK):
        diet.append("Contains pork")
    if "beef" in low or "steak" in low or "short rib" in low:
        diet.append("contains beef")
    if "chicken" in low:
        diet.append("contains chicken")
    if "lamb" in low:
        diet.append("contains lamb")
    if any(s in low for s in ("shrimp", "clams", "calamari")):
        diet.append("contains shellfish")
    if any(f in low for f in ("salmon", "branzino")):
        diet.append("contains fish")
    if any(a in low for a in ALCOHOL):
        diet.append("cooked with wine")
    meatless = not any(x in low for x in PORK + ("beef", "chicken", "lamb", "steak", "short rib", "shrimp", "clams",
                                                     "calamari", "salmon", "branzino"))
    if meatless:
        diet.append("no meat or fish listed, so it may suit vegetarians: confirm the recipe (stock, cheese rennet, anchovy) with the kitchen")
    checks = "Confirm the full recipe with the kitchen before any allergy answer; the menu lists only the main ingredients."
    if wp:
        checks += f" Winter Park card: {wp[0]}. {wp[1]}"
    lines = [f"### {name}{'*' if sig else ''}", "",
             f"**In one line:** {phrase}", "",
             f"**Ingredients:** {ingredients}", "",
             f"**How to present it:** {present}", "",
             f"**Phrases:** \"{phrase}\"", "",
             "**Wines:** The Mount Dora wine list isn't set yet: suggest from the list open in the restaurant.", "",
             "**Allergen notes (to confirm with the kitchen):** " + ("; ".join(notes) if notes else "none listed on the menu, still confirm"), "",
             f"**Kitchen checks:** {checks}", "",
             "**Dietary restrictions:** " + (("; ".join(diet) + ".")[:1].upper() + ("; ".join(diet) + ".")[1:]
                                             if diet else "Confirm with the kitchen."), "", ""]
    return "\n".join(lines)


def main():
    out = ["# Mount Dora dish cards (draft)", "",
           f"{len(D)} dishes from the Mount Dora menu received 27 October 2026. DRAFT: built only from the ingredients "
           "the menu lists, with notes where Winter Park has a related card. No prices yet; desserts and wines aren't on "
           "the menu yet. Every allergen note and dietary line is to confirm with the kitchen: never present them as "
           "confirmed. A star (*) marks a Rome's Flavours signature dish. To be replaced by the kitchen's approved recipes.", "", ""]
    current = None
    for d in D:
        if d[1] != current:
            current = d[1]
            out += [f"## {current}", ""]
            if SECTION[current]:
                out += [SECTION[current], ""]
        out.append(card(*d))
    (HERE / "mount_dora_dish_cards.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {len(D)} cards")


if __name__ == "__main__":
    main()
