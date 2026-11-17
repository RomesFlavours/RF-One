FROM 418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web@sha256:94b1a3c07c33aaacb2937a1ff60ad84654b7a27a60d11f297401bce0b07061de
COPY ["payload/", "/app/"]
COPY ["release/", "/opt/rfone-email-release/"]
RUN python /opt/rfone-email-release/patch_existing.py \
    && python "/app/RF-One Data Store/check_migration_chain.py" --aws-revision t9e120261113
WORKDIR "/app/RF-One Web"
