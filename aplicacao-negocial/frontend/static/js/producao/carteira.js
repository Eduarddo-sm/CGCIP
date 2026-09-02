export function normalizedCarteira(carteira) {
  return String(carteira || "GAMMA").trim().toUpperCase();
}

export function isAlphaCarteira(carteira) {
  return normalizedCarteira(carteira) === "ALPHA";
}

export function isBetaCarteira(carteira) {
  return normalizedCarteira(carteira) === "BETA";
}
