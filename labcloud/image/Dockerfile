# The lab computer: real Debian Linux. One container per learner, started on demand by the Worker.
FROM debian:bookworm-slim AS ttyd
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
# Web terminal (official release, checksum pinned so a tampered download fails the build).
RUN curl -fsSL -o /ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
 && echo "8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55  /ttyd" | sha256sum -c - \
 && chmod 755 /ttyd

FROM --platform=linux/amd64 debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      bash coreutils grep sed gawk findutils less nano file procps python3 ca-certificates \
      git openssh-client iproute2 systemd util-linux tar gzip diffutils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash learner
COPY --from=ttyd /ttyd /usr/local/bin/ttyd
COPY labs /labs
COPY entrypoint.sh learner_shell.sh grader.py /opt/
# Answers (checks) and the pristine seed are root-only: the learner can read only their own home.
RUN chmod -R go-rwx /labs && chmod 755 /opt/*.sh && chmod 644 /opt/grader.py
EXPOSE 7681 8080
ENTRYPOINT ["/opt/entrypoint.sh"]
