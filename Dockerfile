FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:b6cf906e5a84a40ad697017672909fc0a63958163f3bc7bbc56ce84ea6149154
COPY ["03 Software/RF-One Web/role_profile_routes.py", "/app/RF-One Web/role_profile_routes.py"]
COPY ["03 Software/RF-One Web/registry_clover.py", "/app/RF-One Web/registry_clover.py"]
ARG RFONE_RELEASE_REVISION
LABEL org.opencontainers.image.revision=$RFONE_RELEASE_REVISION
