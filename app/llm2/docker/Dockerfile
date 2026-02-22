FROM python:3.11

# We need to pass in UID/GID from host so that files created in the mounted directory
# inside the container have the right ownership on the host filesystem.
ARG USER_ID
ARG GROUP_ID

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# My macOS user's gid already exists in the Linux container image, so only run
# `groupadd` if the gid doesn't exist.
#
# One blemish is that if `groupadd` is called here, the group is created with the
# name `iafisher`, but otherwise it has some other existing name. So all uses of
# `chown` should use the IDs instead of the names.
RUN if ! getent group ${GROUP_ID} >/dev/null; then \
    groupadd --gid ${GROUP_ID} iafisher; \
    fi \
    && useradd --uid ${USER_ID} --gid ${GROUP_ID} --create-home iafisher

ENV HOME=/home/iafisher
ENV PATH="$HOME/.local/bin:$PATH"
ENV XDG_CACHE_HOME="$HOME/.cache"

RUN mkdir -p /venv "$HOME/.cache" \
    && chown -R ${USER_ID}:${GROUP_ID} /venv "$HOME/.cache"

WORKDIR /workspace

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER iafisher

RUN python3 -m venv /venv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENTRYPOINT ["/entrypoint.sh"]
