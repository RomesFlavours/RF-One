FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:f7c93e4eb86f6d5501b97c301a39e902f3a870d1bc998e80b57e986a5da4ed8b
COPY ["03 Software/RF-One Web/role_profile_routes.py", "/app/RF-One Web/role_profile_routes.py"]
COPY ["03 Software/RF-One Web/registry_clover.py", "/app/RF-One Web/registry_clover.py"]
COPY ["03 Software/RF-One Web/templates/_registry_clover.html", "/app/RF-One Web/templates/_registry_clover.html"]
COPY ["03 Software/RF-One Web/templates/_registry_help.html", "/app/RF-One Web/templates/_registry_help.html"]
COPY ["03 Software/RF-One Web/templates/help/registry.html", "/app/RF-One Web/templates/help/registry.html"]
COPY ["03 Software/RF-One Web/templates/help/tips_validation.html", "/app/RF-One Web/templates/help/tips_validation.html"]
COPY ["03 Software/RF-One Web/templates/tips_validation_run.html", "/app/RF-One Web/templates/tips_validation_run.html"]
COPY ["03 Software/RF-One Web/templates/_how_works.html", "/app/RF-One Web/templates/_how_works.html"]
COPY ["03 Software/RF-One Web/tests/test_registry_clover_confirmation.py", "/app/RF-One Web/tests/test_registry_clover_confirmation.py"]
COPY ["03 Software/RF-One Web/templates/role_profiles.html", "/app/RF-One Web/templates/role_profiles.html"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/tips/calculation_run_service.py", "/app/RF-One Data Store/rfone_data_store/tips/calculation_run_service.py"]
RUN python "/app/RF-One Web/tests/test_registry_clover_confirmation.py"
RUN python /app/release_policy_test.py web /app
ARG RFONE_RELEASE_REVISION
LABEL org.opencontainers.image.revision=$RFONE_RELEASE_REVISION
