#!/usr/bin/env bash
# CI helper: loads the Developer ID certificate from the APPLE_CERTIFICATE secret into a
# temporary keychain, before anything gets signed (the bundled engine is signed before the
# app). Writes SIGNING_MODE and APPLE_SIGNING_IDENTITY to $GITHUB_ENV.
#
# With no certificate, or one that can't be used, it falls back to ad-hoc signing with a
# warning, so a manual run still produces a test build. With STRICT=1 (release tags) a bad
# certificate fails the run instead: a release must never ship unsigned by accident.
set -euo pipefail

: "${GITHUB_ENV:?run this from GitHub Actions}"
KEYCHAIN="$RUNNER_TEMP/brieflectures-signing.keychain-db"
P12="$RUNNER_TEMP/certificate.p12"

adhoc() {
  printf 'SIGNING_MODE=adhoc\nAPPLE_SIGNING_IDENTITY=-\n' >> "$GITHUB_ENV"
}

problem() {
  if [ "${STRICT:-0}" = "1" ]; then
    echo "::error title=Code signing::$1"
    exit 1
  fi
  echo "::warning title=Code signing::$1 Building an ad-hoc signed test app instead."
  adhoc
  exit 0
}

if [ -z "${APPLE_CERTIFICATE:-}" ]; then
  echo "No APPLE_CERTIFICATE secret: building an ad-hoc signed test app."
  adhoc
  exit 0
fi

# Secrets pasted from a terminal often carry newlines or spaces; base64 doesn't need them.
if ! printf '%s' "$APPLE_CERTIFICATE" | tr -d '[:space:]' | base64 --decode > "$P12" 2>/dev/null || [ ! -s "$P12" ]; then
  problem "APPLE_CERTIFICATE isn't valid base64. Create it with: base64 -i certificate.p12 | pbcopy"
fi

KEYCHAIN_PASSWORD="$(uuidgen)"
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"

if ! security import "$P12" -k "$KEYCHAIN" -f pkcs12 -P "${APPLE_CERTIFICATE_PASSWORD:-}" \
      -T /usr/bin/codesign -T /usr/bin/security >/dev/null; then
  problem "APPLE_CERTIFICATE couldn't be imported. It must be a .p12 exported from Keychain Access WITH its private key (a .cer file won't work), and APPLE_CERTIFICATE_PASSWORD must be the password chosen when exporting it."
fi
rm -f "$P12"

# Let codesign use the key without a GUI prompt, and put the keychain on the search list.
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN" >/dev/null
# shellcheck disable=SC2046  # the list is one path per word
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')

IDENTITIES="$(security find-identity -v -p codesigning "$KEYCHAIN")"
if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
  if ! grep -qF "\"$APPLE_SIGNING_IDENTITY\"" <<<"$IDENTITIES"; then
    problem "APPLE_SIGNING_IDENTITY ($APPLE_SIGNING_IDENTITY) isn't in the certificate. It contains: $(grep -o '"[^"]*"' <<<"$IDENTITIES" | tr '\n' ' ')"
  fi
  IDENTITY="$APPLE_SIGNING_IDENTITY"
else
  IDENTITY="$(grep -o '"Developer ID Application: [^"]*"' <<<"$IDENTITIES" | head -1 | tr -d '"')"
  [ -n "$IDENTITY" ] || problem "The certificate has no 'Developer ID Application' identity. Create that certificate type (not 'Apple Development') in your Apple Developer account."
fi

echo "Signing as: $IDENTITY"
{
  echo "SIGNING_MODE=developer-id"
  echo "APPLE_SIGNING_IDENTITY=$IDENTITY"
  echo "SIGNING_KEYCHAIN=$KEYCHAIN"
} >> "$GITHUB_ENV"
