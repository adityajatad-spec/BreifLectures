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

Without these secrets the workflow still succeeds, but the app is only ad-hoc signed, and
macOS warns users that it "can't be checked for malicious software". If the secrets exist
but can't be used, a manual run warns and builds an ad-hoc test app anyway; a tag build
fails instead, so a release never ships unsigned by accident.

1. Join the Apple Developer Program ($99/year).
2. In your Apple Developer account, create a **Developer ID Application** certificate. Not
   "Apple Development" and not "Apple Distribution": those can't sign apps distributed
   outside the App Store. Download it and double-click it so it lands in Keychain Access.
3. In Keychain Access → **My Certificates**, expand the certificate to check that a private
   key sits under it. Right-click the certificate → **Export…** → format **.p12**, and set a
   password. (Exporting a `.cer`, or a certificate without its key, is the usual cause of
   "Unable to decode the provided data".)
4. Copy the file as base64: `base64 -i Certificates.p12 | pbcopy`
5. Create an **app-specific password** for your Apple ID at appleid.apple.com.
6. Add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `APPLE_CERTIFICATE` | the base64 text from step 4 (paste exactly; spaces and line breaks are ignored) |
| `APPLE_CERTIFICATE_PASSWORD` | the password from step 3 |
| `APPLE_SIGNING_IDENTITY` | optional; picked from the certificate if left out. If set, it must match exactly, e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | your Apple ID email (for notarization) |
| `APPLE_PASSWORD` | the app-specific password from step 5 |
| `APPLE_TEAM_ID` | your 10-character team ID |

`scripts/macos-signing.sh` loads the certificate into a temporary keychain before anything is
built. It names the exact problem in the run's summary if something is wrong. Both the
bundled engine (`scripts/build-sidecar.sh`) and the app are then signed with that identity,
and Tauri sends the result to Apple for notarization.

> **Not yet verified.** No signed build has run yet. If the notarized app shows
> "The analysis engine stopped" at launch, the hardened runtime is refusing the engine's
> libraries: check `~/Library/Logs/com.brieflectures.desktop/backend.log` and
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
