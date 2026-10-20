#!/bin/sh

if grep -Eiq '^\+[^+].*(mfa\.[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|([A-Za-z0-9_-]*(TOKEN|SECRET|API[_-]?KEY|PASSWORD|PRIVATE[_-]?KEY)[A-Za-z0-9_-]*)[[:space:]]*[:=][[:space:]]*[^[:space:]#]{40,})'; then
    echo "Secret-like content detected in changes; remove it and rotate the credential before retrying." >&2
    exit 1
fi
