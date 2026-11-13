FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:a870a383890078f0e2009839ef69f131b00c11d6b157cac8ab9b3c98666cbe6a
COPY ["03 Software/RF-One Web/templates/role_profiles.html", "/app/RF-One Web/templates/role_profiles.html"]
COPY ["03 Software/RF-One Web/static/css/registry-layout.css", "/app/RF-One Web/static/css/registry-layout.css"]
COPY ["03 Software/RF-One Web/templates/help/registry.html", "/app/RF-One Web/templates/help/registry.html"]
COPY test_registry_layout_release.py /app/test_registry_layout_release.py
RUN python /app/test_registry_layout_release.py /app
