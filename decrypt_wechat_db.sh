#!/bin/bash
# Decrypts WeChat Mac database
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <path_to_encrypted.db> <32_byte_hex_key>"
    exit 1
fi

DB_PATH="$1"
KEY="$2"
OUT_PATH="${DB_PATH}.decrypted.db"

# Check if sqlcipher is installed
if ! command -v sqlcipher &> /dev/null; then
    echo "sqlcipher could not be found. Please install it using: brew install sqlcipher"
    exit 1
fi

sqlcipher "$DB_PATH" <<EOF
PRAGMA key = "x'$KEY'";
PRAGMA cipher_page_size = 1024;
PRAGMA kdf_iter = 4000;
PRAGMA cipher_hmac_algorithm = HMAC_SHA1;
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA1;
ATTACH DATABASE '$OUT_PATH' AS plaintext KEY '';
SELECT sqlcipher_export('plaintext');
DETACH DATABASE plaintext;
EOF

echo "Decrypted database saved to $OUT_PATH"
