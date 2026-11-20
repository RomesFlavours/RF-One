"""The support documents: one short guide per course, to download as a PDF.

Each guide has one section per module, with the points to remember, and
sometimes the words to use. The same facts the AI Trainer teaches and the
test asks, nothing more. Two extra guides are built from the Winter Park dish
cards (pdfs.py): the menu guide and the wine list.
"""

GUIDES = {
    "m1": {
        "intro": "Who we are, what we promise, and why the whole room matters.",
        "sections": [
            ("The promise", [
                "Rome's Flavours gives guests an authentic Italian experience: taste, culinary culture and hospitality.",
                "You lead the table. You help the guest choose; you don't just take the order.",
            ]),
            ("Authenticity without judging", [
                "We serve dishes the way the recipe makes them: the recipe is what makes a dish recognizable.",
                "Explain it warmly. Never make the guest wrong, never sound superior.",
            ]),
            ("The dining room is the stage", [
                "Guests judge the whole experience, including what they see in the back and outside work.",
                "The room is never left empty. When it's quiet, there's always something to clean, tidy or restock.",
                "Service (the dish arrives correctly) and hospitality (the guest feels looked after) go together.",
            ]),
        ],
    },
    "m2": {
        "intro": "Allergies and dietary limits are treated like an injury: prevented with the utmost care.",
        "sections": [
            ("Never change the recipe", [
                "A recipe is never changed to remove an allergen: taking an ingredient off doesn't remove its traces.",
                "Recommend dishes that don't contain it, from allergen information confirmed by the kitchen.",
                "If you aren't sure, the answer is no, and the guest chooses another dish.",
            ]),
            ("Nuts and fish on our menu", [
                "Pine nuts: the basil pesto (gnocchi al pesto, on top of the lasagna, in the meatballs) and the caponata.",
                "Pistachio: Fettuccine Shrimp and Pistachio, cannoli. Hazelnut: the Nutella (pannacotta topping, Campo dei Fiori). Tiramisu: amaretto in the cream, so the kitchen must confirm for a nut allergy.",
                "Fish: anchovy in the Fettuccine Shrimp and Pistachio and the Puttanesca; branzino and salmon. Shellfish (a different allergy from fish): the shrimp in the Fettuccine Shrimp and Pistachio.",
                "Pesto and lasagna are made ahead: nothing can be taken out of them.",
                "Also: eggs in the house pasta (every fettuccine and tagliolini), carbonara and tiramisu; wheat in the pasta, bread, focaccia, pizza, bruschetta and cannoli; dairy in most pasta sauces, every pizza and most desserts.",
                "Pork: Bolognese (pasta and pizza), carbonara (guanciale), meatballs, lasagna, Mercati Traianei (bacon), Dolomiti (speck), the Tuscany board (prosciutto, speck, soppressata), the pizzas with sausage or salami, prosciutto. Confirm with the kitchen.",
                "Alcohol in the cooking (for guests who avoid it): red wine in the Bolognese; white wine in the shrimp fettuccine, Alfredo, gnocchi Sorrento, Vegetable Festival pasta, Vegetable Festival side and lemon butter asparagus; marsala and amaretto in the tiramisu.",
            ]),
            ("Gluten and celiac guests", [
                "No gluten-free pizza.",
                "Gnocchi and the vegan dry pasta contain flour: not gluten free.",
                "There's gluten-free pasta, but flour is used all day in our kitchen: tell a celiac or severe guest honestly.",
                "Tell the kitchen every time. These notes are a guide: the kitchen confirms.",
            ]),
            ("Tell the kitchen every time", [
                "Every allergy, every time, even on a dish you know well. Recipes, suppliers and preparation change.",
                "Children at a table call for extra precautions.",
            ]),
            ("A guest who's been harmed", [
                "Take care of the guest first.",
                "Call the manager on shift immediately. If you're alone in an emergency, call 911.",
                "Write down what the guest says, with the date, time, table and what they ate.",
                "Don't argue, don't admit anything, don't promise anything. Never reply anywhere public.",
            ]),
        ],
    },
    "m7": {
        "intro": "The first minutes decide the evening. The Italian welcome, in three steps.",
        "sections": [
            ("New guest or returning guest", [
                "Open with: \"Good evening, welcome to Rome's Flavours.\" Never the US script \"I'm John, I'll be your server.\"",
                "Find out if they've been before: \"I don't think I've served you before. Has someone on our team?\"",
                "Returning guests: \"Welcome back to Rome's Flavours, it's a pleasure to serve you again.\" Warm, but professional: no hugging, other guests may see favoritism.",
                "Mixed table: give the presentation to the new guests only.",
                "Ask about food intolerances. Thank guests personally when they leave.",
            ]),
            ("Introduce the restaurant and yourself (new guests)", [
                "Like an Italian home: traditional recipes, fresh food made from basic ingredients, prepared to be enjoyed right away.",
                "Truly authentic, with no tricks to meet common taste.",
                "\"My name is John. It will be a pleasure to help you choose what best suits your taste.\"",
                "The goal: turn a new guest into a regular.",
            ]),
            ("Presenting the menu", [
                "Everything is made from scratch, so dishes take the time they need.",
                "We use mainly products imported from Italy.",
                "Chef's signature dishes.",
                "Pasta made in house: fresh cage-free eggs, durum and soft wheat, extra virgin olive oil, a touch of vinegar. Sauces based on tomato, cheese, meat, fish or vegetables.",
                "Pizza dough: three Italian flours, water imported from Italy, natural yeast, a 24-hour rise.",
                "Mains: fish, lamb, beef and chicken.",
                "Wine (new guests): only Italian wine, from small winemakers.",
            ]),
        ],
    },
    "m8": {
        "intro": "What each dish is. The full list of dishes and components is in the Winter Park menu guide.",
        "sections": [
            ("Starters, soups and salads", [
                "Caprese: imported buffalo mozzarella, tomatoes, basil, on arugula.",
                "Prosciutto and Cantaloupe: Parma prosciutto on fresh cantaloupe, with glaze.",
                "Campari tomatoes with parsley-seasoned goat cheese.",
                "Garnished Focaccia and the Tuscany cutting board (prosciutto, speck, hot soppressata, pecorino): for sharing.",
                "Soups (velvet tomato, minestrone) come with homemade bread.",
                "Bruschetta come with a small side salad: goat cheese and sun-dried tomato, tomato, eggplant caponata (pine nuts), Caprese, ricotta and red pepper.",
                "Salads: farro, rich side salad, vegetable garden, chicken.",
            ]),
            ("Pasta and its sauces", [
                "Carbonara: guanciale, eggs, Pecorino, black pepper. No cream.",
                "Bolognese: beef and pork ragu, cooked with red wine.",
                "Shrimp and Pistachio: with garlic, parsley, anchovy, white wine, a touch of tomato.",
                "Puttanesca: anchovy, olives, capers, tomato. Napoletana: tomato, garlic, basil and mint.",
                "Alfredo: mascarpone and Grana. Add truffle cream ($3), mushroom or bacon ($1).",
                "Cacio e Pepe: Pecorino and black pepper. Norma: tomato, fried eggplant, salty ricotta.",
                "Vegetable Festival (pasta): eggplant, zucchini, red pepper, artichoke, tomato, olives, carrot, red onion, arugula, garlic, white wine.",
                "The house pasta is made with eggs and wheat.",
                "Homemade gnocchi: in basil pesto, or Sorrento style with tomato and melted mozzarella.",
            ]),
            ("Our pizzas", [
                "Most are named after places in Rome. Crunchy underneath, soft on top. Every pizza has mozzarella.",
                "Via Napoli: tomato, mozzarella. Testaccio: with hot pepper.",
                "Colosseo: gorgonzola, red peppers, hot salami.",
                "Dolomiti (white): porcini, speck, white truffle oil. Villa Borghese: sausage, mushrooms, truffle oil.",
                "Rome's Flavours: sausage, broccoli, Grana. Mercati Traianei: Amatriciana sauce, red onion, bacon.",
                "Bolognese pizza. Vegetable: Piazza di Spagna (peppers, olives), Trinita dei Monti (eggplant, zucchini, peppers), Via Sicilia (eggplant, salty ricotta).",
            ]),
            ("Mains, sides and desserts", [
                "Every main comes with a choice of one side.",
                "Branzino: whole, oven-baked, head on, or as a filet. Fresh salmon filet.",
                "Minimum times from the menu, for guests in a hurry: whole branzino 25 minutes, branzino filet 15, salmon 10, green peppercorn filet 12, gnocchi Sorrento 12, garnished focaccia 13, Napoletana and Puttanesca 5.",
                "Beef filets: gremolada (garlic, lemon zest, parsley), or green peppercorn (8 oz, cream, Dijon).",
                "Herb lamb (Australian loin T-bones). Homemade meatballs (beef, pork, bread, pesto, bacon). Chicken with olives and capers.",
                "Sides: goat cheese Campari tomato, broccoli and mushrooms, vegetable festival, lemon butter asparagus.",
                "Desserts: tiramisu; pannacotta with Nutella, strawberry, blueberry or espresso; Sicilian cannoli with pistachio; Campo dei Fiori, baked dough with Nutella and powdered sugar, for two to four.",
            ]),
        ],
    },
    "m9": {
        "intro": "The questions guests ask most, and how we answer them.",
        "sections": [
            ("What we don't have", [
                "Kids' menu: no, but kid-friendly dishes: cheese pizza, butter and Parmigiano pasta, olive oil and Parmigiano pasta, Alfredo, Napoli, a side of meatballs. Children can share, or take the rest home.",
                "Chicken parm, chicken penne, spaghetti and meatballs: American interpretations. We cook the traditional recipes of Italian grandmothers. Suggest the closest dish.",
                "Side of pasta: no. A pasta dish from the menu plus a protein.",
                "Bread: yes if a guest asks, but never offered. It's homemade and too much was thrown away.",
            ]),
            ("Cheeses and cured meats", [
                "Buffalo mozzarella: from buffalo milk. Milkier, creamier, softer, more flavor.",
                "Grana Padano: a protected cheese from northern Italy, very close to Parmigiano, aged a little less. It's what we serve when a guest asks for more Parmesan.",
                "Prosciutto: cured pork, not raw. We slice it to order from the whole leg (there's a picture on the wall).",
                "Prosciutto di Parma: protected (DOP), made only around Parma, in Emilia Romagna.",
                "Salame: different parts of the pork, fat and lean, ground together.",
            ]),
            ("Our pasta and pizza dough", [
                "Widths: angel hair very thin, tagliolini like linguine, fettuccine a little wider, pappardelle a wide ribbon.",
                "House pasta: made with eggs, so not vegan.",
                "Vegan dry pasta: very good, not made in house, about 20 minutes, not gluten free.",
                "Gnocchi: potato and flour, cut by hand. Not gluten free.",
                "Pizza dough: Italian flours, natural yeast, water imported from Italy (San Benedetto). Crusty underneath, soft on top, not a thin crust. No gluten-free pizza.",
                "Vegan guests: the pizza dough and the gnocchi have no animal products, but every pizza has mozzarella and both gnocchi dishes have cheese. Tell the guest honestly, and ask the front of house lead and the kitchen what can be offered.",
            ]),
        ],
    },
    "m3": {
        "intro": "Describe honestly, and suggest for the guest in front of you.",
        "sections": [
            ("Describe it truthfully", [
                "Describe from the dish cards and the menu.",
                "Say fresh, house-made, imported or signature only where the menu or card says so.",
                "Check the guest knows what they chose: describe the taste, so the dish meets their expectation.",
                "If the card doesn't answer, check with the kitchen and come back.",
            ]),
            ("No changes to dishes", [
                "First ask: is it an allergy or a preference? An allergy follows the allergy rule.",
                "For a preference, explain warmly how the dish is made and why, and suggest a dish closer to their taste.",
                "Don't promise variations. Sticking to the recipes also helps the kitchen.",
            ]),
            ("Suggest for the guest, not for the tip", [
                "Listen to their tastes and their occasion, and be able to say why your suggestion suits them.",
                "Complete the meal (a wine, a starter) when it adds to the experience.",
                "A good recommendation can be a cheaper bottle.",
            ]),
        ],
    },
    "m10": {
        "intro": "Only Italian wine, from small importers. The wines on our list are in the wine list guide.",
        "sections": [
            ("What wine is", [
                "Yeasts turn the sugars in grape juice into alcohol: that's fermentation.",
                "Harvest: earlier for fresh whites to drink young, later for wines to age.",
                "Destemming and crushing, then fermentation.",
                "Aging: weeks to months in steel or cement; months to years in barrels or barriques.",
                "Bottling, then one to three months' rest in the bottle before sale.",
            ]),
            ("Italian wines, and why ours", [
                "Only Italian wine, because everything here is authentically Italian.",
                "Italy has more grape varieties than anywhere: many climates, centuries as separate states, many soils.",
                "North: dry, lighter, sophisticated (except Barolo and Amarone). Center: medium-bodied, rich in nuances. South: fruity, full-bodied, hints of berries.",
                "Small importers: wines other restaurants and stores don't have, better mid-range wines, a fairer price for the guest.",
            ]),
            ("Suggesting a wine", [
                "Red or white?",
                "Red: dry or fruity? Light, medium or full-bodied?",
                "White: sweeter or more acidic?",
                "Then suggest two or three wines. Explain each one's main characteristics simply, never technically.",
                "Keep in mind which wines are open in the fridge.",
                "Samples: only from bottles already open. Open one bottle for a sample only if the table wants a whole bottle: bring the flier with the other samples and an empty shot glass, and open it at the table.",
            ]),
            ("Opening a bottle at the table", [
                "Bring the clean bottle without shaking it. Show the label: the name, then the vintage.",
                "Cut the capsule below the lip and put it in your pocket.",
                "Corkscrew in the center, screw in, stop before the last turn. Lever out in two steps.",
                "Smell the cork. Vinegar: apologize and bring another bottle.",
                "Take the tasting glass by the stem, without leaving fingerprints, and pour about a quarter inch for the person who ordered to taste.",
                "After their OK, serve women first or start from the right, from each guest's right, label showing, without touching the glasses and without drops.",
            ]),
        ],
    },
    "m11": {
        "intro": "From the order pad to the goodbye, the same way every time.",
        "sections": [
            ("The order pad", [
                "Remember the spot you approached the table from: that's your pivot.",
                "Number the guests from there, well spaced, and write each order next to its number.",
                "Go straight to the POS.",
            ]),
            ("Entering it in the POS", [
                "Always sign the previous person out and sign in as yourself. Back to the home screen.",
                "Open the right table and set the right number of guests.",
                "Each item under the right guest. A shared starter under the table. A bottle under the table, or under the guest who's offering it.",
                "Changes with the modifiers, never by hand.",
                "Never prepare a drink that isn't entered.",
            ]),
            ("Sending it to the kitchen", [
                "Starters: add 'First' right away. Print for the kitchen first (drinks unchecked), then for the front of house bar (all items). Hang it on the bar.",
                "Mains: print the whole order again, starters included, kitchen first. Starters already served: mark them with a marker. Not served yet: tell the kitchen to switch the order.",
                "Desserts: kitchen first, then front of house.",
            ]),
            ("The check and Arrivederci", [
                "Check every item served is on it. Print it when the table seems done and keep it ready.",
                "Bring it only when the guest asks, then step away.",
                "Take the card or cash as soon as it's down, thank them, pay it at the POS, release the table.",
                "The signed check and cash tips go in your own bank bag. Never cash or checks in a pocket.",
                "Say goodbye with 'Arrivederci': see you again.",
            ]),
        ],
    },
    "m12": {
        "intro": "The Italian way to serve: elegant, safe and the same every time.",
        "sections": [
            ("Glasses and drinks", [
                "Glasses above the plate, slightly right; water closest. Don't invade the next guest's space. No water glass: the drink goes in front of the right corner of the plate.",
                "Stemmed glasses by the stem, two at a time. Stemless glasses held low.",
                "Every drink opened at the table, except fountain drinks, juices and wine by the glass.",
                "Pour toward 10 to 12 o'clock, label visible. Never pour toward the outside of your arm.",
                "Refills: water, leave a quarter empty; wine, up to a third. From bottles on the table, without touching the glasses.",
            ]),
            ("Serving the plates", [
                "Two plates at a time (three only in a rush). Palm up, forearm level, at least 8 inches from your body, thumb along the rim.",
                "Just above the table, never at face height.",
                "Announce each dish.",
                "Serve from the right, clear from the left: walk around the table. If the right is impossible, serve from the left, never reaching across the table.",
                "Never serve if the table hasn't been cleared from the previous course.",
                "Children first, then ladies, then men, oldest first.",
                "Set the table for the next course first. Empty plates before a shared dish.",
            ]),
            ("Clearing the table", [
                "Clear when everyone has finished, unless a guest asks. Ask before taking a plate. A plate left untouched for a long time: politely ask if you can take it.",
                "One plate at a time, from the left. Never stack on the table. Up to three on the left arm.",
                "Booth: farthest plates first. Never kneel on the seat.",
                "Before dessert, clear every dish and all the silverware.",
                "Never use a glass as a trash can, hold a glass by the rim, or touch silverware where it was in the mouth.",
                "Silverware comes on a service plate. Napkins stay on the table.",
            ]),
        ],
    },
    "m4": {
        "intro": "At Rome's Flavours the whole team watches the whole room.",
        "sections": [
            ("Eyes on the whole room", [
                "Stand where you can see the most tables. Never stay in the back without a task.",
                "Scan the room like a radar, even while folding silverware.",
                "The door first: if the host isn't there, welcome the guest yourself, whatever you're doing.",
                "Plates in the kitchen window: take them out, tell the table's server, or serve them.",
                "Empty tables set and ready; every guest has what they need, at any table.",
                "A table that's waited too long and gone quiet: ask the kitchen for the timing, then apologize and reassure.",
            ]),
            ("Specific questions", [
                "\"How is the carbonara?\", not \"Do you need anything else?\"",
                "Keep an eye on your tables without imposing.",
                "The standard: not servile, and no 'something more' beyond it.",
            ]),
            ("A guest waiting in a busy moment", [
                "Acknowledge them quickly, even when you're busy.",
                "Tell the truth about the wait, without blaming the kitchen or colleagues.",
                "Get help from the team.",
            ]),
            ("Speeding up or slowing down", [
                "Slow down: the order bar is full, or the room is nearly empty.",
                "Speed up: few tickets at peak time, a full room, many tables, or the table is booked again soon.",
                "To speed up: talk less, take drinks and starters together, take the mains right after the drinks, check they're enjoying the food while pre-bussing, leave the dessert menu while clearing, print the check after dessert.",
                "Only if the table must be freed urgently: pre-bus the dessert plates and leave the check on the table, saying \"No rush.\"",
                "To slow down: talk more about the restaurant and the food, take one course at a time.",
            ]),
        ],
    },
    "m5": {
        "intro": "Problems are solved fastest when they're visible early.",
        "sections": [
            ("The three A's", [
                "Acknowledge the problem.",
                "Apologize (if it isn't your fault, for not having been able to prevent it).",
                "Act: propose a solution.",
                "Report it to the manager on shift, and tell the kitchen about every food complaint, even when the guest says it's nothing.",
            ]),
            ("No free food or drinks", [
                "Servers never give food or drinks for free.",
                "A gesture is decided by the front of house lead on shift, up to $50. Above that, Pino.",
                "Every gesture is recorded.",
            ]),
            ("An order already sent", [
                "Tell the guest you'll check whether it's been started, without promising.",
                "Go to the front of house lead right away; they decide with the kitchen lead.",
                "The sooner the kitchen knows, the less is wasted.",
            ]),
            ("Make problems visible early", [
                "Your own mistake: tell the kitchen and the manager right away.",
                "What makes a mistake bigger is the time before anyone hears about it.",
                "Asking for help or reporting a mistake is not held against you.",
            ]),
        ],
    },
    "m6": {
        "intro": "Who decides what, how to work with the host, and the basics of a good shift.",
        "sections": [
            ("Who's who on a shift", [
                "Front of house lead: the floor, sections, service, the schedule, gestures up to $50.",
                "Kitchen lead: dishes, recipes, allergen confirmation, changes to orders already sent (with the front of house lead).",
                "Manager on shift, immediately: an injury, a harmed guest or allergic reaction, food safety, an alcohol problem. The manager calls Pino.",
            ]),
            ("Working with the host", [
                "The host's priorities: 1 the podium and drawing guests in; 2 welcoming, seating, updating OpenTable; 3 setting tables; 4 helping servers reset; 5 other help on request.",
                "Ask the host for help as little as possible.",
                "When the host isn't there: cover the podium (never empty), welcome and seat guests, update OpenTable right away, bring menus, check the silverware.",
                "Resetting your own tables is your responsibility.",
            ]),
            ("A table that isn't yours", [
                "Help with the need, or tell the colleague in charge or the manager.",
                "Respect every role, from host to manager. Tips also depend on the kitchen's work.",
            ]),
            ("Professional behavior", [
                "Clean, professional image as food safety rules require: hair collected, short nails, no rings.",
                "No phone on duty: it stays in the service room.",
                "Never leave the room empty. Keep busy. Prevent waste.",
                "No drugs or alcohol. Arrive 10 minutes early.",
                "Changes in availability: tell the manager by text as soon as you know.",
            ]),
        ],
    },
}

# Extra guides attached to a course card, besides the course's own guide.
EXTRA = {"m2": ["menu"], "m8": ["menu"], "m9": ["menu"], "m10": ["wines"]}
EXTRA_TITLES = {"menu": "Winter Park menu guide", "wines": "Our wine list", "safety": "Safety card"}
