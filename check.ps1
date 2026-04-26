$ErrorActionPreference = "Stop"

Push-Location backend
try {
  python -m pytest
}
finally {
  Pop-Location
}

Push-Location frontend
try {
  npm run lint
  npm run build
}
finally {
  Pop-Location
}
