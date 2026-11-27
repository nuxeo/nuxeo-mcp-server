ARG NUXEO_VERSION=2025

FROM docker-private.packages.nuxeo.com/nuxeo/nuxeo:${NUXEO_VERSION}

ARG BUILD_TAG=unknown
ARG SCM_REF=unknown
ARG VERSION=unknown
ARG NUXEO_PACKAGES=nuxeo-web-ui

LABEL org.nuxeo.mcp-tests.build-tag=$BUILD_TAG
LABEL org.nuxeo.mcp-tests.scm-ref=$SCM_REF
LABEL org.nuxeo.mcp-tests.version=$VERSION

USER root
# install RPM Fusion free repository
RUN dnf -y install --nogpgcheck https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-9.noarch.rpm \
    && dnf -y --enablerepo=ol9_codeready_builder install ffmpeg \
    && dnf clean all
USER 900

# Install remote packages
RUN --mount=type=secret,id=CLID,env=CLID \
    --mount=type=secret,id=CONNECT_URL,env=CONNECT_URL \
    /install-packages.sh --clid ${CLID} --connect-url ${CONNECT_URL} \
    $(echo "$NUXEO_PACKAGES" | tr ',' ' ')
