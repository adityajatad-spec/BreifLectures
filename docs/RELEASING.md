# Releasing the macOS app

## Build it yourself (on a Mac)

Prerequisites: Xcode Command Line Tools (`xcode-select --install`), Rust (`rustup`),
Node 20+ and Python 3.11+.

```sh
make setup
make app
```

The app and installer end up in `desktop/src-tauri/target/release/bundle/`:
`macos/BriefLectures.app` and `dmg/BriefLectures_<version>_aarch64.dmg`.

A local build without an Apple certificate is unsigned. It runs on your own Mac but will
be blocked on anyone else's. For a quick test build that others can open with
right-click → Open, ad-hoc sign it: `APPLE_SIGNING_IDENTITY=- make app`.

## Release through GitHub Actions

`.github/workflows/release.yml` builds on an Apple Silicon runner:

- **Actions → Release (macOS) → Run workflow** gives you the `.dmg` as a downloadable artifact.
- **Pushing a tag** such as `git tag v0.3.0 && git push origin v0.3.0` also attaches it to
  a draft GitHub release, which you publish by hand.

### Signing and notarization (needed for public distribution)

Without these the workflow still succeeds, but the app is only ad-hoc signed and macOS will
warn users that it "can't be checked for malicious software". To fix that:

1. Join the Apple Developer Program ($99/year).
2. Create a **Developer ID Application** certificate. Export it from Keychain Access as a `.p12`.
3. Create an **app-specific password** for your Apple ID at appleid.apple.com.
4. Add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `APPLE_CERTIFICATE` | `base64 -i certificate.p12` output |
| `APPLE_CERTIFICATE_PASSWORD` | the `.p12` export password |
| `APPLE_SIGNING_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | your Apple ID email |
| `APPLE_PASSWORD` | the app-specific password |
| `APPLE_TEAM_ID` | your 10-character team ID |

The Tauri CLI picks these up and signs the app and the bundled engine, then notarizes the
result. `scripts/build-sidecar.sh` also signs the Python libraries inside the engine with the
same identity.

> **Not yet verified.** This sandbox can't run macOS, so nothing here has been signed or
> notarized for real. The first signed CI run is the real test. If the notarized app shows
> "The analysis engine stopped" at launch, the engine's libraries are being refused by the
> hardened runtime: check `~/Library/Logs/com.brieflectures.desktop/backend.log` and
> `desktop/src-tauri/Entitlements.plist`.

## Bumping the version

The version appears in five places; keep them in sync:
`desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml`, `desktop/package.json`,
`web/package.json` and `backend/pyproject.toml`.

## Not done yet

- **Auto-update.** Add `tauri-plugin-updater`, generate an update-signing key pair
  (`npx tauri signer generate`), keep the private key in a `TAURI_SIGNING_PRIVATE_KEY`
  secret, and point the updater at the GitHub release's `latest.json`. This needs a key only
  you should hold, so it isn't set up here.
- **Intel Macs.** Only Apple Silicon is built. Intel needs a second job on an x86_64 macOS
  runner, because PyInstaller can't cross-compile the engine.
- **The identifier** `com.brieflectures.desktop` is a placeholder. Change it to a domain you
  own before the first public release: macOS ties settings, keychain entries and the app's
  data folder to it, so changing it later strands existing users' libraries.
