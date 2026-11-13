"""English card presentation; provenance stays in internal metadata only."""
import html


def translate(cards):
    wp, md = cards
    wp.update(
        presentation='Fresh house-made fettuccine with shrimp, pistachio and a touch of tomato, served with four large sautéed shrimp.',
        ingredients='Fresh egg pasta, shrimp, pistachio, extra virgin olive oil, garlic, parsley, anchovy, white wine and a touch of tomato.',
        allergens='Includes shrimp (crustaceans), anchovy (fish), pistachio and eggs. Confirm wheat, the complete recipe and cross-contact precautions with the kitchen. Allergy suitability has not been validated.',
        training=[
            'The portion includes four large sautéed shrimp.',
            'Anchovy is an ingredient even though it is not mentioned in the dish name.',
            'The sauce is described as creamy. Whether it contains cream or cheese must be confirmed with the kitchen.',
            'A ten-minute preparation indication requires confirmation. Do not promise this waiting time to guests.',
        ],
        questions=[['Does it contain fish as well as shrimp?', 'Anchovy is included. Confirm the current recipe with the kitchen.'],
                   ['Does it contain cream or cheese?', 'This has not been confirmed. Check with the kitchen.']],
        verification='Confirm the current recipe, complete allergens, permitted modifications, plating photograph and preparation time.')
    md.update(
        presentation='Fresh house-made fettuccine with shrimp, pistachio, garlic, parsley, white wine and olive oil.',
        ingredients='Shrimp, pistachio, garlic, parsley, white wine and olive oil. The pasta is made fresh in-house daily.',
        allergens='Includes shrimp (crustaceans) and pistachio. Confirm the pasta ingredients, other allergens and cross-contact precautions with the kitchen. Allergy suitability has not been validated.',
        training=[
            'Present this restaurant’s preparation using the ingredients listed above.',
            'The number of shrimp has not been confirmed for Mount Dora.',
            'The presence or absence of anchovy and tomato must be confirmed with the kitchen.',
            'Eggs in the pasta, preparation method and preparation time require confirmation for this restaurant.',
        ],
        questions=[['How many shrimp are served?', 'The portion count has not been confirmed. Check with the kitchen.'],
                   ['Does it contain anchovy or tomato?', 'Their presence or absence has not been confirmed. Check with the kitchen.']],
        verification='Confirm the complete recipe, pasta ingredients, portion, allergens, permitted modifications, preparation time and plating photograph.')
    return cards


def render(card, style):
    e = html.escape
    peer = 'mount-dora' if card['restaurant_key'] == 'winter-park' else 'winter-park'
    training = ''.join('<li>'+e(x)+'</li>' for x in card['training'])
    questions = ''.join('<p><strong>'+e(q)+'</strong><br>'+e(a)+'</p>' for q, a in card['questions'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(card['title'])} · {e(card['restaurant_name'])}</title><style>{style}</style>
<main><nav aria-label="Restaurants"><a href="{peer}.html">Open {'Mount Dora' if peer == 'mount-dora' else 'Winter Park'}</a><a href="#help" data-how-works="dish-card" onclick="document.getElementById('help').showModal();return false">How this card works</a></nav>
<p>{e(card['restaurant_name'])} › Fresh pasta</p><article><span class="badge">Pending kitchen validation</span><h1>{e(card['title'])}</h1>
<img src="shrimp-pistacchio.jpg" alt="Fettuccine with shrimp and pistachio"><p class="note">Current plating for this restaurant requires confirmation.</p>
<h2>At the table</h2><p><strong>How to describe it</strong><br>{e(card['presentation'])}</p><p><strong>Ingredients</strong><br>{e(card['ingredients'])}</p><p><strong>Allergy requests</strong><br>{e(card['allergens'])}</p><p><strong>Modifications and substitutions</strong><br>Check with the kitchen before confirming any changes to a guest.</p>
<details><summary>Training · Get to know the dish</summary><ul>{training}</ul><h2>Frequently asked questions</h2>{questions}</details>
<details><summary>Items to confirm</summary><p>{e(card['verification'])}</p></details></article>
<footer>Version {card['content_version']} · Kitchen validation pending.</footer></main>
<dialog id="help" aria-labelledby="help-title"><button class="close" aria-label="Close" onclick="this.closest('dialog').close()">×</button><h2 id="help-title">How this card works</h2><p>Check the restaurant above the dish name. At the table provides a short presentation, ingredients and guidance for guest questions. Open Training for more detail and frequently asked questions.</p><p>Kitchen validation is pending. Unconfirmed details cannot be used to guarantee allergen absence, modifications or waiting times. Use the restaurant link above to open the other restaurant’s card. This preview is read-only.</p><button onclick="this.closest('dialog').close()">Close</button></dialog></html>'''
