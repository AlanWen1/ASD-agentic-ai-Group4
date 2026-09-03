# Scripts

Project build, testing, and deployment scripts, per the repository
structure required in the project spec.

- `build/build-all.sh` — builds every service's Docker image via the root
  `docker-compose.yml`.
- `test/test-all.sh` — runs each student module's Python test suite
  (compile-check + pytest) from the repository root, the same checks each
  student's own GitHub Actions workflow runs individually.
- `deploy/` — placeholder for the Release 2 cloud deployment scripts
  (Azure or AWS). Not implemented yet since Release 2 hasn't started.

Run these from the repository root, e.g. `./scripts/test/test-all.sh`.
