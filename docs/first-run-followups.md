# First-run scope and remaining design

The first tranche lives in the canonical public Skill. It composes existing
Core host, local discovery-decision and update-inspection reports, with a safe
non-executing default when CLI provenance is unknown. It does not add a Core
scanner, installer, updater, server or new universal discovery API.

## Existing mechanisms reused

- CLI existence lookup and existing consent-gated SHA-verified bootstrap.
- `host list` / `host doctor` / `host install`: host manifests, executable
  detection, pins and official open-source installation channels.
- `dcc-types --dcc-type`: separate installation, registration, direct readiness,
  exact-call and real-host gates, using the local FileRegistry only.
- `update inspect`: recorded versus executing versions and official evidence.
- `update discover`: provider-qualified official catalogs independent of the
  CLI's hardcoded/bundled software list. Source failures remain partial/unknown.
- Existing cached async refresh, lock, TTL and failure backoff; no synchronous
  whole-ecosystem check inserted into normal commands.
- Existing feedback route/bundle/file for actual diagnostic Findings, plus a
  separate local software-request draft rather than inventing a failure.

## Remaining Core design, not implemented by this tranche

1. **Safe startup boundary.** Host/list/dcc-types handlers have read-only query
   semantics but normal startup may activate a staged update. A future Core
   change can extend a verified early gate after testing lifecycle/logging,
   registry freshness, and package provenance. Do not label today's entire
   invocation mutation-free. Inspection support needs release capability
   metadata, not a guessed minimum version.
2. **Cross-provider change evidence.** Keep a versioned, bounded snapshot identity
   and freshness per provider. Compare added/removed capabilities and changed
   requirements by provider-qualified identity. Treat unavailable/truncated
   snapshots as inconclusive; catalog changes do not establish release dates,
   runtime compatibility or issue fixes. Current interfaces do not promise a
   complete machine-queryable feature/release diff.
3. **Notification persistence.** Current Skill guidance deduplicates within a task;
   cross-agent, cross-session notification acknowledgments need an owner and a
   bounded state contract. Reuse existing update caching rather than invent a
   separate polling daemon.

4. **Provider identities.** A source-owned, versioned crosswalk must join host
   manifest IDs to canonical product and adapter identities. The current report
   combines exact IDs only and exposes unmatched IDs; for example Core host
   `substance` and product `substance3d_painter` stay separate. Do not fuzzy-join
   names or rewrite host command arguments based on a display name.

## Studio and Rez design boundary

Before implementation, agree on the following contract with a concrete studio
consumer and test matrix:

- Which owner supplies machine, user, project, session and explicit-command
  configuration; document precedence and provenance without dumping values.
- Existing executable overrides and host locks remain authoritative until a
  reviewed migration says otherwise. An agent cannot silently replace a pin.
- Batch deployment needs a reviewed per-environment plan, dry run, exact artifact
  identities, compatibility evidence, approval scope, job-drain window,
  rollback method and per-target receipt. Partial success is not fleet success.
- Rez integration should consume resolved package context/version constraints
  and expose a supported adapter boundary. Do not mutate the global environment,
  resolve/execute untrusted packages, or introduce a parallel version resolver.
- Different installed and running versions are expected during staged rollout;
  report both and verify actual host runtime after the approved activation.

These are design questions only. This PR does not implement fleet deployment,
new environment-variable precedence, Rez resolution or automatic upgrades.
