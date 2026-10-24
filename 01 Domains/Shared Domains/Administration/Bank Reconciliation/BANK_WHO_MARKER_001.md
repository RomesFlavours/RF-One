# BANK_WHO_MARKER_001

1. Request: show the WHO selected by an extraction rule with marker-style highlighting in the matched transaction preview.
2. Implementation: the same extractor can return the exact source segments before, inside and after its selection. Ordinary extraction still returns the same uppercase WHO. Preview rows carry these segments; the renderer escapes all three and wraps only the selected WHO in a yellow mark. Leading/trailing padding and reference codes remain outside the mark. Original casing and description text remain unchanged. Source reconstruction must match exactly before the renderer highlights it.
3. The Extracted WHO column remains visible. No classification or application behavior changes. Photos do not invent description matches. No schema changes.
4. Checks: ACH selection, Zelle references, numbers within names, empty WHO, original text reconstruction and HTML escaping. Synthetic HTTP preview verifies three real fixture rows and unchanged decisions. JavaScript, Python and Jinja syntax checks.
5. Restore references: deployment output includes bank_before.db, code_before and deployment.json.
