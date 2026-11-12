FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:ebc997cff06999e96ed34eab395d00a146d8e61c0eb37a5ad40ec0a09030be71
RUN --mount=type=bind,source=navigation,target=/navigation,ro python /navigation/apply.py
ARG RFONE_RELEASE_REVISION
LABEL org.opencontainers.image.revision=$RFONE_RELEASE_REVISION
