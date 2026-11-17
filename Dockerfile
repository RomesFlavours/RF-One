# HOME_REMOVE_SELECTION_OLD_001 — overlay on the live rfone-web image
# (registry-trainee-c89bd42ba6cc); only the Home template changes.
FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:dc8f3355b79c1f530c3619396c04e1b87265b1175feee04f0499c4f348348268
COPY release/remove_selection_old_home.py /tmp/remove_selection_old_home.py
RUN python /tmp/remove_selection_old_home.py /app && rm /tmp/remove_selection_old_home.py
