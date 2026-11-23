"""The Server role's pills, grouped into training courses.

A pill is the smallest unit of knowledge that is scored (Pino's pill model:
the score always belongs to one pill, a course is never scored). Selection
records what the person already shows on each pill; Training teaches the
pills that were not shown, course by course. On screen a pill is a "module"
and a pill group is a "course".

Every pill's "known" text is what a person has to show, in their own words,
for the pill to count. The first pills come from the Server AI Trainer manual
v0.2 (sections 3 and 4), which Pino received on 28 October 2026. The pills
added on 3 November 2026 come from Pino's own training documents: The Service
at Rome's Flavours, the Customers FAQ, Wines, and the Winter Park menu with
its components (see content/pino_service_manual.md). Where the two differ,
the newer manual wins and the difference is listed for Pino to confirm.

Course ids are kept from the first version (m1 to m6) so progress already
saved in a browser and the hiring team's reviews keep working. The list's
order is the order the courses are shown and taught in.

"sources" names the reference material the AI Trainer gets for that course,
besides the manual (see prompts.py).
"""

MODULES = [
    {
        "id": "m1",
        "title": "Who we are",
        "subtitle": "Rome's Flavours, the promise and the guest's experience",
        "sources": [],
        "pills": [
            {
                "id": "m1.promise",
                "title": "The promise",
                "known": "Explains that Rome's Flavours gives guests an authentic Italian experience of taste, culinary culture and hospitality, and that the Server leads the table: helps the guest choose, not just takes the order.",
                "scenario": "A guest says: 'It's just another Italian place, right?' What do you tell them about this restaurant?",
            },
            {
                "id": "m1.authentic",
                "title": "Authenticity without judging",
                "known": "Knows that dishes are served as the menu describes them because the recipe is what makes the dish recognizable, and explains it warmly, without making the guest wrong or sounding superior.",
                "scenario": "A guest laughs and says real Italians would never eat the way you do here. How do you answer?",
            },
            {
                "id": "m1.stage",
                "title": "The dining room is the stage",
                "known": "Understands that guests judge the whole experience, that the room is never left empty, that the uniform and behavior in the back matter too, and that service (the dish arriving correctly) and hospitality (the guest feeling looked after) must go together.",
                "scenario": "It's a slow afternoon. Your tables are fine and two colleagues are chatting by the bar. What do you do with your time, and why?",
            },
        ],
    },
    {
        "id": "m2",
        "title": "Guest safety",
        "subtitle": "Allergies, dietary limits and emergencies",
        "safety_critical": True,
        "sources": ["dish_cards", "service"],
        "pills": [
            {
                "id": "m2.allergy",
                "title": "Allergies: never change the recipe",
                "known": "Knows that a recipe is never changed to remove an allergen because traces remain; recommends dishes that don't contain it, from allergen information confirmed by the kitchen; if not sure, the answer is no and the guest chooses another dish.",
                "scenario": "A guest is allergic to pistachio and asks you to just leave the pistachios off the dish they want. What do you do?",
            },
            {
                "id": "m2.nuts",
                "title": "Nuts and fish on our menu",
                "known": "Names where nuts and fish hide on our menu: pine nuts in the basil pesto (gnocchi al pesto, on top of the lasagna, in the meatballs) and in the caponata; pistachio in the shrimp fettuccine and the cannoli; hazelnut in the Nutella (Campo dei Fiori, the pannacotta topping); amaretto in the tiramisu, which the kitchen must confirm for a nut allergy; anchovy (a fish) in the shrimp fettuccine and the puttanesca; shrimp (a shellfish, which is a different allergy from fish) in the shrimp fettuccine; and knows the pesto and the lasagna are made ahead, so nothing can be taken out of them.",
                "scenario": "A guest with a nut allergy wants the homemade meatballs and asks if there's anything to worry about. What do you tell them?",
            },
            {
                "id": "m2.gluten",
                "title": "Gluten and celiac guests",
                "known": "Knows there's no gluten-free pizza; the gnocchi and the vegan dry pasta contain flour, so they aren't gluten free; there is gluten-free pasta, but the kitchen uses flour all day, so a celiac or severe guest is told that honestly; and the kitchen is told every time.",
                "scenario": "A guest says they're celiac and would love the gnocchi or a pizza. What do you tell them?",
            },
            {
                "id": "m2.tell_kitchen",
                "title": "Tell the kitchen every time",
                "known": "Tells the kitchen about every allergy, every time, even on a dish they know well, because recipes, suppliers and preparation change; takes extra precautions with children.",
                "scenario": "A regular guest with a nut allergy orders the same dish they have every week, and says 'you know me, it's always fine.' What do you do?",
            },
            {
                "id": "m2.harmed",
                "title": "A guest who's been harmed",
                "known": "Takes care of the guest first, calls the manager on shift immediately (911 if alone in an emergency), writes down what the guest says with date, time, table and what they ate, doesn't argue, admit or promise anything, and never replies anywhere public.",
                "scenario": "A guest at your table says their lips are tingling after eating. What do you do, in order?",
            },
        ],
    },
    {
        "id": "m7",
        "title": "The welcome",
        "subtitle": "The first minutes at the table, Italian style",
        "sources": ["service"],
        "pills": [
            {
                "id": "m4.welcome",
                "title": "New guest or returning guest",
                "known": "Greets with a smile, 'Good evening, welcome to Rome's Flavours', and finds out whether the guests have eaten with us before ('I don't think I've served you before, has someone on our team?'), without the US script 'I'm John, I'll be your server'; welcomes returning guests back warmly but professionally, no hugging, because other guests may see favoritism; gives the full presentation only to the new guests at a mixed table; asks about food intolerances; and thanks guests personally when they leave.",
                "scenario": "A family of four sits down at your table. Show me what you'd say in the first minute.",
            },
            {
                "id": "m7.introduce",
                "title": "Introduce the restaurant and yourself",
                "known": "For new guests, presents the restaurant in a few sentences, like an Italian home: traditional recipes, fresh food made from basic ingredients, prepared to be enjoyed right away, authentic with no tricks to meet common taste; then introduces themself as the person who will help them choose ('My name is John, it will be a pleasure to help you choose what best suits your taste'); knows the goal is to turn a new guest into a regular.",
                "scenario": "A couple tells you it's their first time at Rome's Flavours. What do you say before they open the menu?",
            },
            {
                "id": "m7.menu_tour",
                "title": "Presenting the menu",
                "known": "Tells new guests that everything is made from scratch so dishes take the time they need, that we use mainly products imported from Italy, and walks through the menu's areas: the Chef's signature dishes; pasta made in house (fresh cage-free eggs, durum and soft wheat, extra virgin olive oil, a touch of vinegar) with sauces based on tomato, cheese, meat, fish or vegetables; pizza dough from three Italian flours, water imported from Italy and natural yeast, rising 24 hours; fish, lamb, beef and chicken; and, for new guests, that we serve only Italian wine from small winemakers.",
                "scenario": "The new couple asks: 'So what's good here, how does the menu work?' Walk them through it in under a minute.",
            },
        ],
    },
    {
        "id": "m8",
        "title": "Our menu",
        "subtitle": "What every dish is, from starters to desserts",
        "sources": ["dish_cards", "service"],
        "pills": [
            {
                "id": "m8.starters",
                "title": "Starters, soups and salads",
                "known": "Can describe the starters from their components: Caprese (imported buffalo mozzarella, tomatoes, basil, arugula), Prosciutto and Cantaloupe (Parma prosciutto, cantaloupe, glaze), Campari tomatoes with goat cheese, the Garnished Focaccia and the Tuscany cutting board for sharing; knows the soups (velvet tomato, minestrone) come with homemade bread, the bruschetta come with a small side salad, and the caponata has pine nuts.",
                "scenario": "A table of four wants something to share to start, and one of them doesn't eat meat. What do you suggest, and how do you describe it?",
            },
            {
                "id": "m8.pasta",
                "title": "Pasta and its sauces",
                "known": "Knows the pasta dishes and what makes each one: carbonara (guanciale, eggs, Pecorino, black pepper, no cream), Bolognese (beef and pork ragu with red wine), shrimp and pistachio (with anchovy, garlic, white wine), puttanesca (anchovy, olives, capers), Napoletana, Alfredo (mascarpone and Grana, with truffle cream for $3 or mushroom or bacon for $1), cacio e pepe, Norma (fried eggplant, salty ricotta), the vegetable festival, and the homemade gnocchi with basil pesto or Sorrento style with tomato and melted mozzarella.",
                "scenario": "A guest says: 'I want pasta, something creamy but not too heavy, and I don't eat pork.' What do you suggest, and what do you steer them away from?",
            },
            {
                "id": "m8.pizza",
                "title": "Our pizzas",
                "known": "Knows most pizzas are named after places in Rome and can say what's on the main ones: Via Napoli (tomato, mozzarella), Testaccio (with hot pepper), Colosseo (gorgonzola, red peppers, hot salami), Dolomiti (white, porcini, speck, truffle oil), Villa Borghese (sausage, mushrooms, truffle oil), Rome's Flavours (sausage, broccoli, Grana), Mercati Traianei (Amatriciana sauce, red onion, bacon), the Bolognese pizza, and the vegetable ones (Piazza di Spagna, Trinita dei Monti, Via Sicilia); and that the crust is crunchy underneath and soft on top.",
                "scenario": "A guest asks what the Colosseo and the Dolomiti are, and which one is less spicy. How do you answer?",
            },
            {
                "id": "m8.mains",
                "title": "Mains, sides and desserts",
                "known": "Knows every main comes with a choice of one side; can describe the branzino (whole and oven-baked, head on, at least 25 minutes, or as a filet, about 15), the salmon (about 10 minutes), the beef filets (gremolada, or green peppercorn with cream and Dijon), the herb lamb, the meatballs (beef, pork, bread, pesto, bacon) and the chicken with olives and capers; names the sides; and describes the desserts: tiramisu, pannacotta with its toppings, Sicilian cannoli with pistachio, and Campo dei Fiori, baked dough with Nutella and powdered sugar for two to four guests.",
                "scenario": "A guest is torn between the whole branzino and the salmon, and they're in a hurry. What do you tell them?",
            },
        ],
    },
    {
        "id": "m9",
        "title": "Guest questions",
        "subtitle": "The questions guests ask most, and our answers",
        "sources": ["faq", "dish_cards"],
        "pills": [
            {
                "id": "m9.off_menu",
                "title": "What we don't have",
                "known": "Answers the common requests warmly: no kids' menu, but kid-friendly dishes (cheese pizza, butter and Parmigiano pasta, olive oil and Parmigiano pasta, Alfredo, Napoli, a side of meatballs), which children can share or take home; dishes like chicken parmigiana or spaghetti and meatballs are American interpretations, and we cook the traditional recipes of Italian grandmothers, so suggests the closest dish; no side of pasta, but a pasta dish plus a protein; bread if a guest asks, but never offered, because it's homemade and was being thrown away.",
                "scenario": "A family asks for the kids' menu, and the dad asks if you have chicken parm. How do you answer both?",
            },
            {
                "id": "m9.ingredients",
                "title": "Cheeses and cured meats",
                "known": "Explains the ingredients guests ask about: buffalo mozzarella is made from buffalo milk, creamier, milkier and more flavorful than regular mozzarella; Grana Padano is a protected cheese from northern Italy, very close to Parmigiano but aged less, and that's what we serve when a guest asks for more Parmesan; prosciutto is cured pork, not raw, sliced to order from the whole leg; Prosciutto di Parma is protected and made only around Parma; salame is made from different parts of the pork ground together, not one cut.",
                "scenario": "A guest asks: 'Is prosciutto raw? And can I get some more Parmesan?' What do you say and do?",
            },
            {
                "id": "m9.pasta_dough",
                "title": "Our pasta and pizza dough",
                "known": "Knows the pasta shapes by width (angel hair very thin, tagliolini like linguine, fettuccine a little wider, pappardelle a wide ribbon); that the house pasta has eggs so it isn't vegan, while the dry pasta is vegan, not made in house, takes about 20 minutes and isn't gluten free; that the gnocchi are potato and flour, cut by hand, and not gluten free; that the pizza dough is made with Italian flours, natural yeast and water imported from Italy, crusty underneath and soft on top, not a thin crust, and not gluten free; and that the pizza dough and the gnocchi have no animal products, but every pizza on the menu has mozzarella and both gnocchi dishes have cheese, so a vegan guest is told that honestly and the front of house lead and the kitchen say what can be offered.",
                "scenario": "A vegan guest asks which pasta and which pizza they can have. What do you tell them?",
            },
        ],
    },
    {
        "id": "m3",
        "title": "Helping the guest choose",
        "subtitle": "Describing dishes honestly and suggesting for the guest",
        "sources": ["dish_cards"],
        "pills": [
            {
                "id": "m3.describe",
                "title": "Describe it truthfully",
                "known": "Describes dishes and wines from the dish cards and the menu, uses words like fresh, house-made, imported or signature only where the menu says so, checks the guest knows what they chose, and checks with the kitchen when the card doesn't answer.",
                "scenario": "A guest points at the menu and asks: 'What's this one like? Is it good?' How do you answer?",
            },
            {
                "id": "m3.no_changes",
                "title": "No changes to dishes",
                "known": "First asks whether it's an allergy or a preference; for a preference explains how the dish is made and why, and suggests a dish closer to what the guest likes; doesn't promise variations, which also helps the kitchen.",
                "scenario": "A guest wants the carbonara with cream and chicken. What do you say?",
            },
            {
                "id": "m3.suggest",
                "title": "Suggest for the guest, not for the tip",
                "known": "Recommends by listening to tastes and situation, can explain why a suggestion suits that guest, completes the meal (a wine, a starter) when it adds to the experience, and knows that a good recommendation can be a cheaper bottle too.",
                "scenario": "A couple is celebrating an anniversary and asks you to pick the wine. How do you choose what to suggest?",
            },
        ],
    },
    {
        "id": "m10",
        "title": "Italian wine",
        "subtitle": "Our wines, how to suggest them and how to open a bottle",
        "sources": ["wine", "dish_cards"],
        "pills": [
            {
                "id": "m10.basics",
                "title": "What wine is",
                "known": "Can say simply that wine is grape juice whose sugars yeast turns into alcohol, and the steps: harvest (earlier for fresh whites, later for wines to age), destemming and crushing, fermentation, settling and aging (in steel or cement for weeks to months, in barrels or barriques for months to years), bottling and a rest in the bottle.",
                "scenario": "A guest asks you: 'What's the difference between a young white and a wine that's been aged?' How do you explain it simply?",
            },
            {
                "id": "m10.italy",
                "title": "Italian wines and why ours",
                "known": "Knows we serve only Italian wine because everything here is authentically Italian; that Italy has more grape varieties than anywhere, because of its climates, its history of many separate states, and its many soils; the general rule: northern wines dry, lighter and more sophisticated (except Barolo and Amarone), central wines medium-bodied and rich in nuances, southern wines fruity and full-bodied; and that we buy from small importers, so we have wines other restaurants and stores don't, better mid-range wines, and fair prices.",
                "scenario": "A guest says: 'I only know Chianti. Why don't you have any French or California wines?' How do you answer, and what do you offer them?",
            },
            {
                "id": "m10.suggest",
                "title": "Suggesting a wine",
                "known": "Finds the guest's taste with a few questions (red or white; for red, dry or fruity, and light, medium or full-bodied; for white, sweeter or more acidic) and suggests two or three wines; gives samples only of bottles already open, when there's time; opens one bottle only for a sample, and only when the table wants a whole bottle, bringing a shot glass and opening it at the table.",
                "scenario": "A guest wants a bottle of red but can't decide and asks to taste two. What do you do?",
            },
            {
                "id": "m10.open",
                "title": "Opening a bottle at the table",
                "known": "Knows the ritual: bring the clean bottle without shaking it and show the label, saying the name and vintage; cut the capsule below the lip and pocket it; insert the corkscrew in the center and screw in, stopping before the last turn; lever out the cork in two steps; smell it for vinegar (if so, apologize and bring another bottle); pour about a quarter inch for the person who ordered to taste; after their OK, serve women first or start from the right, label showing, without touching the glasses and without drops; and explains the wine's main characteristics simply, never technically.",
                "scenario": "You bring a bottle to a table of four and when you smell the cork it smells like vinegar. Walk me through what you did before that, and what you do now.",
            },
        ],
    },
    {
        "id": "m11",
        "title": "Taking the order",
        "subtitle": "The order pad, the POS, the check and the payment",
        "sources": ["service"],
        "pills": [
            {
                "id": "m11.pad",
                "title": "The order pad",
                "known": "Memorizes the spot they approached the table from, numbers the guests from there (the pivot), well spaced on the pad, writes each guest's order next to their number, and goes straight to the POS without doing anything else on the way.",
                "scenario": "A table of six orders drinks and starters all at once. How do you write it down so nobody's plate goes to the wrong person?",
            },
            {
                "id": "m11.pos",
                "title": "Entering it in the POS",
                "known": "Always signs out the last person and signs in as themself, returns to the home screen, opens the right table and sets the right number of guests; enters each item under the right guest, a shared starter under the table, a bottle of wine under the table or under the guest who's offering it; enters anything the kitchen must know (the 'First' modifier, a listed add-on like the truffle cream, an allergy) with the modifiers, never by hand; never prepares a drink that isn't entered.",
                "scenario": "You're at the POS and the screen still shows a colleague's name and their last table. What do you do before entering your order?",
            },
            {
                "id": "m11.fire",
                "title": "Sending it to the kitchen",
                "known": "Adds the modifier 'First' to starters right away; prints the starters for the kitchen first, with drinks unchecked, then for the front of house bar with everything, and hangs it on the bar; for the mains prints the whole order again, starters included, kitchen first then front of house, marking the starters with a marker if they've been served, or telling the kitchen to switch the order if they haven't; desserts go the same way, kitchen first.",
                "scenario": "Your table's starters are already on the table and they now order their mains. What exactly do you print, in what order, and what do you do with the ticket?",
            },
            {
                "id": "m11.check",
                "title": "The check and Arrivederci",
                "known": "Checks every item served is on the check, prints it when the table seems done and keeps it ready, brings it only when the guest asks and steps away; takes the card or cash as soon as it's placed, thanks them, pays it at the POS and releases the table; puts the signed check and cash tips in their own bank bag and never carries cash or checks in a pocket; and says goodbye with 'Arrivederci', which means see you again.",
                "scenario": "Your table has finished dessert and is chatting happily. When do you bring the check, and what happens after the guest puts down their card?",
            },
        ],
    },
    {
        "id": "m12",
        "title": "Serving the table",
        "subtitle": "Glasses, plates and clearing, the Italian way",
        "sources": ["service"],
        "pills": [
            {
                "id": "m12.drinks",
                "title": "Glasses and drinks",
                "known": "Places glasses above the plate slightly to the right, water closest, without invading the next guest's space; holds stemmed glasses by the stem (so two at a time) and stemless ones low; uncorks every drink at the table except fountain drinks, juices and wine by the glass; pours toward 10 to 12 o'clock with the label visible; refills water leaving a quarter empty and wine only up to a third, and from bottles on the table without touching the glasses.",
                "scenario": "You're bringing four glasses of red wine by the glass and a bottle of sparkling water to a table. How do you carry and serve them?",
            },
            {
                "id": "m12.plates",
                "title": "Serving the plates",
                "known": "Carries two plates (three only in a rush), palm up, forearm level, plates at least 8 inches (a hand's width) from the body, thumb along the rim; lifts them above the table but never at face height; announces each dish; serves from the guest's right and clears from the left, walking around the table; serves children first, then ladies, then men, oldest first; sets the table for the next course first, and brings empty plates before a shared dish.",
                "scenario": "You're carrying the mains to a table of five: two kids, two women and a man. The table still has bread plates on it. What do you do?",
            },
            {
                "id": "m12.clearing",
                "title": "Clearing the table",
                "known": "Clears only when everyone has finished unless a guest asks, and asks before taking a plate; removes plates one at a time from the left, never stacking them on the table, up to three on the left arm; in a booth starts with the farthest plates and never kneels on the seat; clears all dishes and silverware before dessert; never uses a glass as a trash can, never holds a glass by the rim or silverware by the part that was in the mouth, brings silverware on a service plate, and never takes the napkins away.",
                "scenario": "At a table of four, two guests have finished their pasta and two are still eating. One of the finished guests pushes their plate toward you. What do you do?",
            },
        ],
    },
    {
        "id": "m4",
        "title": "Leading the room",
        "subtitle": "Eyes on the whole room, timing and attention",
        "sources": ["service"],
        "pills": [
            {
                "id": "m4.radar",
                "title": "Eyes on the whole room",
                "known": "Stands where they can see the most tables and never stays in the back without a task; scans the room like a radar even while folding silverware; covers the podium and the door when the host isn't there; takes plates from the kitchen window as soon as they appear, tells the table's server or serves them; checks empty tables are set and that every guest has what they need, notifying the colleague or acting; and goes to a table that has waited too long to apologize and reassure, after asking the kitchen for the timing.",
                "scenario": "You're folding silverware. A couple is standing at the door, two plates are sitting in the kitchen window, and a colleague's table is looking around. What do you do, in what order?",
            },
            {
                "id": "m4.specific",
                "title": "Specific questions",
                "known": "Asks specific questions ('How is the carbonara?') instead of open ones ('Do you need anything else?'), keeps an eye on the table without imposing, and gives the standard: neither servile nor 'something more' beyond it.",
                "scenario": "Ten minutes after the food arrives, you go back to the table. What do you ask, and what are you looking for?",
            },
            {
                "id": "m4.waiting",
                "title": "A guest waiting in a busy moment",
                "known": "Acknowledges the waiting guest quickly even when busy, tells the truth about the wait without blaming the kitchen or colleagues, and gets help from the team when needed.",
                "scenario": "It's Saturday night, you're in the weeds, and a table you haven't greeted yet is looking around for someone. What do you do?",
            },
            {
                "id": "m4.speed",
                "title": "Speeding up or slowing down",
                "known": "Slows down when the order bar is full (so the kitchen can keep up) or the room is nearly empty; speeds up when the bar is empty at peak time, the room is full, they have many tables, or the table is booked again soon; speeds up by talking less, taking drinks and starters together, taking the mains right after the drinks, leaving the dessert menu while clearing, and printing the check after dessert; slows down by talking more about the restaurant and the food and taking one course at a time.",
                "scenario": "It's 7 pm, the room is full, but there are only two tickets on the order bar. What do you change in how you serve your tables?",
            },
        ],
    },
    {
        "id": "m5",
        "title": "When something goes wrong",
        "subtitle": "Complaints, mistakes and orders already sent",
        "sources": [],
        "pills": [
            {
                "id": "m5.three_a",
                "title": "The three A's",
                "known": "Acknowledges the problem, apologizes (for not having prevented it, if it isn't their fault) and acts with a solution; reports it to the manager on shift and tells the kitchen about every food complaint, even when the guest says it's nothing.",
                "scenario": "A guest says her pasta is too salty, but tells you not to worry about it. What do you do?",
            },
            {
                "id": "m5.no_comps",
                "title": "No free food or drinks",
                "known": "Knows Servers never give food or drinks for free: a gesture is decided by the front of house lead on shift up to $50, above that by Pino, and every gesture is recorded.",
                "scenario": "A table had a long wait and is unhappy. Would you take the dessert off the bill? Walk me through what you'd do.",
            },
            {
                "id": "m5.sent_order",
                "title": "An order already sent",
                "known": "Tells the guest they'll check whether it's been started, without promising the change, and goes to the front of house lead right away, who decides with the kitchen lead; knows speed reduces waste.",
                "scenario": "A guest changes their mind about a main course two minutes after you sent the order. What do you do?",
            },
            {
                "id": "m5.visible",
                "title": "Make problems visible early",
                "known": "Tells the kitchen and the manager about their own mistake right away, understands that what makes a mistake bigger is the time before anyone hears about it, and that asking for help or reporting a mistake is not held against them.",
                "scenario": "You realize you forgot to put in a side dish, and the guest hasn't noticed yet. What do you do?",
            },
        ],
    },
    {
        "id": "m6",
        "title": "The team and the house",
        "subtitle": "Who decides what, the host, and professional behavior",
        "sources": ["service"],
        "pills": [
            {
                "id": "m6.whos_who",
                "title": "Who's who on a shift",
                "known": "Knows the front of house lead runs the floor and gestures up to $50, the kitchen lead the dishes and allergen confirmation, and the manager on shift any injury, harmed guest, food safety or alcohol problem, who calls Pino.",
                "scenario": "During a shift: a guest wants a free dessert, a cook says an allergen isn't confirmed, and a guest seems drunk. Who do you go to for each?",
            },
            {
                "id": "m6.host",
                "title": "Working with the host",
                "known": "Knows the host's priorities in order: hold the podium and draw guests in, welcome and seat them and update OpenTable, set tables, help servers reset tables, then other help on request; asks the host for help as little as possible; when the host isn't there, covers the podium (coordinating so it's never empty), welcomes and seats guests, updates OpenTable right away to avoid double bookings, brings menus and checks the silverware; and knows resetting their own tables is their own responsibility.",
                "scenario": "The host is walking a party to their table and two more guests come in the door. You're about to ask the host to help you reset a table. What do you do instead?",
            },
            {
                "id": "m6.other_table",
                "title": "A table that isn't yours",
                "known": "Helps with a need at another Server's table or tells the colleague in charge or the manager, respects everyone's role from host to manager, and knows tips also depend on the kitchen's work.",
                "scenario": "A guest at a colleague's table waves you over and asks for the check. What do you do?",
            },
            {
                "id": "m6.conduct",
                "title": "Professional behavior",
                "known": "Knows the basics: clean professional image as food safety rules require, no phone on duty, never leave the room empty, keep busy, prevent waste, no drugs or alcohol, arrive 10 minutes early, and tell the manager by text about changes in availability.",
                "scenario": "What does a good shift look like for you, from the moment you arrive to when you leave?",
            },
        ],
    },
]

PILLS = {p["id"]: dict(p, module=m["id"]) for m in MODULES for p in m["pills"]}
MODULE_BY_ID = {m["id"]: m for m in MODULES}
