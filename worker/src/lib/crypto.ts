/**
 * AES-256-GCM encryption for BYOK API keys at rest.
 * Uses Web Crypto API available in Cloudflare Workers.
 *
 * Encrypted format: base64(iv + ciphertext)
 * - iv: 12 bytes (GCM standard)
 * - ciphertext: includes GCM auth tag appended by Web Crypto
 */

const IV_LENGTH = 12;

async function deriveKey(hexKey: string): Promise<CryptoKey> {
  const keyBytes = new Uint8Array(
    hexKey.match(/.{2}/g)!.map((b) => parseInt(b, 16))
  );
  return crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, [
    "encrypt",
    "decrypt",
  ]);
}

export async function encrypt(
  plaintext: string,
  hexKey: string
): Promise<string> {
  const key = await deriveKey(hexKey);
  const iv = new Uint8Array(IV_LENGTH);
  crypto.getRandomValues(iv);

  const encoded = new TextEncoder().encode(plaintext);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded)
  );

  // Concatenate iv + ciphertext, then base64-encode
  const combined = new Uint8Array(iv.length + ciphertext.length);
  combined.set(iv);
  combined.set(ciphertext, iv.length);

  return btoa(String.fromCharCode(...combined));
}

export async function decrypt(
  encrypted: string,
  hexKey: string
): Promise<string> {
  const key = await deriveKey(hexKey);
  const combined = Uint8Array.from(atob(encrypted), (c) => c.charCodeAt(0));

  const iv = combined.slice(0, IV_LENGTH);
  const ciphertext = combined.slice(IV_LENGTH);

  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    key,
    ciphertext
  );

  return new TextDecoder().decode(decrypted);
}

/**
 * Try to decrypt a value; if it fails (e.g. legacy plaintext), return as-is.
 */
export async function decryptOrPassthrough(
  value: string,
  hexKey: string
): Promise<string> {
  try {
    return await decrypt(value, hexKey);
  } catch {
    return value;
  }
}
