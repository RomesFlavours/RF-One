FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:fb932cb91a6df290f456bf7e09488f299b5f45197be590f093e46ab1461836c8
COPY ["03 Software/RF-One Data Store/migrations/versions/r9a120261113_registry_training_aws_release.py", "/app/RF-One Data Store/migrations/versions/r9a120261113_registry_training_aws_release.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/people_registry.py", "/app/RF-One Data Store/rfone_data_store/people_registry.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/rfone_recovery_service.py", "/app/RF-One Data Store/rfone_data_store/rfone_recovery_service.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/student_registry.py", "/app/RF-One Data Store/rfone_data_store/student_registry.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/technical/account_email.py", "/app/RF-One Data Store/rfone_data_store/technical/account_email.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/technical/smtp_email.py", "/app/RF-One Data Store/rfone_data_store/technical/smtp_email.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/training/workspace.py", "/app/RF-One Data Store/rfone_data_store/training/workspace.py"]
COPY ["03 Software/RF-One Web/app.py", "/app/RF-One Web/app.py"]
COPY ["03 Software/RF-One Web/templates/help/registry.html", "/app/RF-One Web/templates/help/registry.html"]
COPY ["03 Software/RF-One Web/training_activation_guard.py", "/app/RF-One Web/training_activation_guard.py"]
COPY ["03 Software/RF-One Web/training_integration.py", "/app/RF-One Web/training_integration.py"]
COPY ["03 Software/Shared UI/check_how_works.py", "/app/Shared UI/check_how_works.py"]
COPY ["03 Software/Shared UI/how_works_registry.json", "/app/Shared UI/how_works_registry.json"]
COPY release_test_registry.py /app/release_test_registry.py
RUN python /app/release_test_registry.py web /app
