FROM debian:13 as builder

ARG DEBIAN_FRONTEND=noninteractive
ARG RUST_VERSION=1.90.0

ARG TMKMS_GIT_URL=https://github.com/iqlusioninc/tmkms.git
ARG TMKMS_GIT_REF=v0.14.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential ufw curl jq snapd \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.3 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build

RUN git clone ${TMKMS_GIT_URL} /build/tmkms-src \
 && cd /build/tmkms-src \
 && git checkout ${TMKMS_GIT_REF}

RUN set -eux; cd /build/tmkms-src; \
    cargo install tmkms --features=softsign


FROM debian:13-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates libssl3 libstdc++6 libgcc-s1 \
      python3 \
      python3-pip \
      python3-venv \
      vim iputils-ping net-tools dnsutils curl gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade google-cloud-secret-manager --break-system-packages


RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 tmkms

RUN mkdir -p /etc/tmkms /var/lib/tmkms /var/log/tmkms \
 && chown -R tmkms:tmkms /etc/tmkms /var/lib/tmkms /var/log/tmkms

COPY --from=builder /root/.cargo/bin/tmkms /bin/tmkms
ADD import.py /
ADD entrypoint.sh /

RUN chmod ug+x /entrypoint.sh

VOLUME ["/etc/tmkms", "/var/lib/tmkms", "/opt/tmkms"]

#USER tmkms

ENTRYPOINT ["/entrypoint.sh"]



