FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends chrony \
    && rm -rf /var/lib/apt/lists/*
COPY deployment/time/chrony.conf /etc/chrony/chrony.conf
EXPOSE 123/udp
# -x serves the container/host clock without modifying the laptop's clock.
CMD ["chronyd", "-d", "-x", "-f", "/etc/chrony/chrony.conf"]
