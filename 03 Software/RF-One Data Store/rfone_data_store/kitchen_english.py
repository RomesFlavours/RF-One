"""Reviewed Kitchen English content mapping; identifiers and source evidence stay intact."""
import re

TRANSLATIONS={
 'Ricetta':'Recipe','Preparazione':'Preparation','Impiattamento':'Plating','Montaggio':'Assembly',
 'Preparazone':'Preparation','Pulire':'Clean','Spadellamento':'Toss in the pan',
 'Scorza di 1 limone':'Zest of 1 lemon','aggiungere e mescolare':'Add and mix',
 'Alcool':'Alcohol','Maionese':'Mayonnaise','Vaniglia':'Vanilla','Polenta Istantanea':'Instant Polenta',
 'Colatura di Cetara':'Cetara Anchovy Sauce','Colatura di Alici di Cetara':'Cetara Anchovy Sauce',
 'Pistacchio Nuts':'Pistachio Nuts','Mostard':'Mustard','Bakin Powder':'Baking Powder',
 'Balsamic Vinager Modena':'Modena Balsamic Vinegar','Cantalupe':'Cantaloupe',
 'Chicken Thigs':'Chicken Thighs','Cheese Cuttinboard A':'Cheese Board A',
 'Cheese Cuttinboard B':'Cheese Board B','Cheese Cuttinboard C':'Cheese Board C',
 'Clams-Vongole':'Clams','Flour 00 Pizzeria':'Type 00 Pizza Flour','Flour Semola':'Semolina Flour',
 'Fontina ITA':'Italian Fontina','Provolone ITA':'Italian Provolone',
 'Mozzarella-Bufala Fresh':'Fresh Buffalo Mozzarella','Mozzarella-Shreeded':'Shredded Mozzarella',
 'Pesto Genovese':'Genoese Pesto','Potato Jellow':'Yellow Potatoes','Potato Small Jellow':'Small Yellow Potatoes',
 'Ricotta Salata':'Salted Ricotta','Salame - Piccante ITA':'Italian Spicy Salami',
 'Salame- Soppressata Usa':'US Soppressata Salami','Salmone Filet Frozen Norwegian':'Frozen Norwegian Salmon Fillet',
 'Tomato-Sun Dry-ITA':'Italian Sun-Dried Tomatoes','Truffle Black Fesh':'Fresh Black Truffle',
 'Vinagr Apple':'Apple Cider Vinegar','Wipped Cream':'Whipped Cream','Veggy Base Knorr':'Knorr Vegetable Base',
 'ZZ - Conteiner - Alluminium 3lt':'ZZ - Aluminium Container - 3 L','ZZ-Food Generico':'ZZ-Generic Food',
 'Anice Star':'Star Anise','Apricot Dry':'Dried Apricot','CornStarc':'Cornstarch',
 'Bruschetta & Soupe':'Bruschetta & Soup','CockTail':'Cocktail','Employees Meals':'Employee Meals',
 'Menu Drinks':'Drinks Menu','TakeAway':'Takeaway','X-OUT':'Off Menu','Verificare':'To Verify',
 'Besciamella':'Bechamel Sauce','Erbs Oil':'Herb Oil','Broccoli e Mashrooms':'Broccoli and Mushrooms',
 'Grissini speziati':'Spiced Breadsticks','Cacio e Pepe':'Cheese and Pepper',
 'Cannelloni Bolognesi':'Bolognese Cannelloni','Caponata Siciliana':'Sicilian Caponata',
 'Caponata Verdure':'Vegetable Caponata','Chichen Olives and Carpers':'Chicken with Olives and Capers',
 'Chichen Thigs Marinated':'Marinated Chicken Thighs','Chicken Thigs Salad':'Chicken Thigh Salad',
 'Carrot Julienn':'Julienned Carrot','Chocosouffle':'Chocolate Souffle','Chocosuffle':'Chocolate Souffle',
 'Chocosoufflè Felipe':'Chocolate Souffle - Felipe','Branzino Filet':'Sea Bass Fillet',
 'Branzino Whole':'Whole Sea Bass','Filet Gemolada (For Two)':'Fillet with Gremolata (For Two)',
 'Filet Tartare':'Fillet Tartare','Fresh Pasta-one Serving':'Fresh Pasta - One Serving',
 'Grana Padano Grated':'Grated Grana Padano','Lamb Scottadito':'Grilled Lamb Chops',
 'Mushed Potato':'Mashed Potato','Mushroom Streamed':'Steamed Mushrooms','Octopuss Boiled':'Boiled Octopus',
 'Potato Rosted':'Roasted Potato','Proscuitto - Side':'Prosciutto - Side','Ripieno Cannoli':'Cannoli Filling',
 'Ripieno Ricotta e Spinaci':'Ricotta and Spinach Filling','Rise Boiled':'Boiled Rice',
 'Salsiccia Alla Romana - Side':'Roman-Style Sausage - Side','Salsiccia alla Romana':'Roman-Style Sausage',
 'Sicilain Tuna Filet':'Sicilian Tuna Fillet','Sorbetto and Prosecco':'Sorbet and Prosecco',
 'Soupe Asparagus Cream':'Cream of Asparagus Soup','Soupe/Broccoli Cheese Soup':'Broccoli and Cheese Soup',
 'Soupe/Mushroom Soup':'Mushroom Soup','Soupe/Onion Soupe':'Onion Soup',
 'Soupe/Zucchini And Cheese':'Zucchini and Cheese Soup','Spinach for Totellini':'Spinach for Tortellini',
 'Spread Broccoli-Grana-Pistacchio':'Broccoli, Grana Padano and Pistachio Spread',
 'Tortellini di Lonza e Prosciutto':'Pork Loin and Prosciutto Tortellini',
 'Straccetti, Arugula & Truffle':'Beef Strips, Arugula & Truffle','Tuna Pistacchio':'Tuna with Pistachio',
 'Vegetal Fettuccine':'Vegetable Fettuccine','Shrimp & Pistacchio':'Shrimp & Pistachio',
 'Shrimps Soupe':'Shrimp Soup','Pesto Basil Genovese':'Genoese Basil Pesto',
}


def translate(value):
    if not isinstance(value,str) or not value.strip():return value
    stripped=value.strip()
    if stripped in TRANSLATIONS:return TRANSLATIONS[stripped]
    match=re.match(r'^(F-|L-|Pr\d+-)(.*)$',stripped,re.I)
    if match and match.group(2).strip() in TRANSLATIONS:
        return match.group(1)+TRANSLATIONS[match.group(2).strip()]
    # Correct the Italian word in otherwise English operational instructions.
    return re.sub(r'\balcool\b','alcohol',value,flags=re.I)
