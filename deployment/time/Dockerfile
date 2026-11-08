FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends chrony \
    && rm -rf /var/lib/apt/lists/*
COPY deployment/time/chrony.conf /etc/chrony/chrony.conf
EXPOSE 123/udp
# A stopped container retains its pidfile; PID 1 is reused on restart.
# Remove only this service's stale pidfile before starting its sole daemon.
# -x serves the container/host clock without modifying the laptop's clock.
CMD ["sh", "-c", "rm -f /tmp/chronyd.pid && exec chronyd -d -x -f /etc/chrony/chrony.conf"]
