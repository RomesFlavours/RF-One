FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:6f228bf45a50b32bec1cc94c032296e90d12b39f603a4c50087853f902f25812
COPY ["03 Software/RF-One Data Store/migrations/versions/t9e120261113_training_enrollment_aws.py", "/app/RF-One Data Store/migrations/versions/t9e120261113_training_enrollment_aws.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/selection/workspace_models.py", "/app/RF-One Data Store/rfone_data_store/selection/workspace_models.py"]
COPY ["03 Software/RF-One Data Store/rfone_data_store/training/enrollment.py", "/app/RF-One Data Store/rfone_data_store/training/enrollment.py"]
COPY ["03 Software/RF-One Web/static/css/training-workspace.css", "/app/RF-One Web/static/css/training-workspace.css"]
COPY ["03 Software/RF-One Web/static/js/training-enrollment.js", "/app/RF-One Web/static/js/training-enrollment.js"]
COPY ["03 Software/RF-One Web/templates/help/training_enrollment.html", "/app/RF-One Web/templates/help/training_enrollment.html"]
COPY ["03 Software/RF-One Web/templates/help/training_enrollment_activation.html", "/app/RF-One Web/templates/help/training_enrollment_activation.html"]
COPY ["03 Software/RF-One Web/templates/help/training_students.html", "/app/RF-One Web/templates/help/training_students.html"]
COPY ["03 Software/RF-One Web/templates/training_workspace/enrollment.html", "/app/RF-One Web/templates/training_workspace/enrollment.html"]
COPY ["03 Software/RF-One Web/templates/training_workspace/enrollment_activation.html", "/app/RF-One Web/templates/training_workspace/enrollment_activation.html"]
COPY ["03 Software/RF-One Web/templates/training_workspace/students.html", "/app/RF-One Web/templates/training_workspace/students.html"]
COPY ["03 Software/RF-One Web/test_training_enrollment_release.py", "/app/RF-One Web/test_training_enrollment_release.py"]
COPY ["03 Software/RF-One Web/training_enrollment_routes.py", "/app/RF-One Web/training_enrollment_routes.py"]
COPY ["03 Software/RF-One Web/training_workspace_routes.py", "/app/RF-One Web/training_workspace_routes.py"]
COPY ["03 Software/Shared UI/how_works_registry.json", "/app/Shared UI/how_works_registry.json"]
COPY ["03 Software/Training/ENROLLMENT.md", "/app/Training/ENROLLMENT.md"]
COPY release-enrollment-manifest.json /app/release-enrollment-manifest.json
COPY release_test_enrollment.py /app/release_test_enrollment.py
RUN python /app/release_test_enrollment.py
