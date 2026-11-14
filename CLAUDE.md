# Hackathon (pikkuinen)

Standing context for the `pikkuinen-hackathon` Claude session. Keep this file current.

## Goal

(Not set yet: fill in the hackathon, its theme, deadline and what we are building.)

## Machine

- Host `pikkuinen`, Ubuntu, 4 cores, 7.6 GB RAM shared by many services; memory is tight.
  This session is capped at 2.6 GB (systemd drop-in 50-memory.conf).
- No passwordless sudo: anything needing root is a command for the user to run.
- Don't touch other projects' services (camscraper, pmarb, home automation, etc.).
- Secrets go in files with mode 600 and are never printed in chat or committed.
