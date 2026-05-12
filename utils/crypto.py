# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import os
import struct

import aiofiles

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import Iterator, Optional, Protocol, Tuple


class AsyncReader(Protocol):
    async def read(self, size: int) -> bytes: ...


def generate_rsa_keypair(
    key_size: int = 4096,
) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """
    Generate an RSA key pair.
    Returns a tuple of (private_key, public_key).

    Parameters:
        key_size (int): Size of the RSA key in bits. Default is 4096.

    Returns:
        Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]: The generated RSA private and public keys.
    """

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )
    return private_key, private_key.public_key()


def serialize_private_key_to_pem(
    private_key: rsa.RSAPrivateKey,
    password: bytes,
) -> bytes:
    """
    Serialize the private key to PEM format.
    If a password is provided, the key will be encrypted.

    Parameters:
        private_key (rsa.RSAPrivateKey): The RSA private key to serialize.
        password (bytes): The password to encrypt the private key.

    Returns:
        bytes: The PEM-formatted private key.
    """

    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )


def serialize_public_key_to_pem(
    public_key: rsa.RSAPublicKey,
) -> bytes:
    """
    Serialize the public key to PEM format.

    Parameters:
        public_key (rsa.RSAPublicKey): The RSA public key to serialize.

    Returns:
        bytes: The PEM-formatted public key.
    """

    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def deserialize_private_key_from_pem(
    pem_data: bytes,
    password: bytes,
) -> rsa.RSAPrivateKey:
    """
    Deserialize a PEM-formatted private key.
    If the key is encrypted, provide the password.

    Parameters:
        pem_data (bytes): The PEM-formatted private key data.
        password (bytes): The password to decrypt the private key.

    Returns:
        rsa.RSAPrivateKey: The deserialized RSA private key.
    """

    if not isinstance(password, bytes):
        password = password.encode("utf-8")
    if not isinstance(pem_data, bytes):
        pem_data = pem_data.encode("utf-8")

    return serialization.load_pem_private_key(pem_data, password=password)


def deserialize_public_key_from_pem(
    pem_data: bytes,
) -> rsa.RSAPublicKey:
    """
    Deserialize a PEM-formatted public key.

    Parameters:
        pem_data (bytes): The PEM-formatted public key data.

    Returns:
        rsa.RSAPublicKey: The deserialized RSA public key.
    """
    return serialization.load_pem_public_key(pem_data)


def validate_private_key_password(
    private_key_pem: bytes,
    password: bytes,
) -> bool:
    """
    Validate if the provided password can decrypt the private key.

    Parameters:
        private_key_pem (bytes): The PEM-formatted private key data.
        password (bytes): The password to validate.

    Returns:
        bool: True if the password is correct, False otherwise.
    """
    if not isinstance(password, bytes):
        password = password.encode("utf-8")
    if not isinstance(private_key_pem, bytes):
        private_key_pem = private_key_pem.encode("utf-8")

    return bool(deserialize_private_key_from_pem(private_key_pem, password))


def encrypt_string(
    public_key: rsa.RSAPublicKey,
    plaintext: str,
    aes_key: Optional[bytes] = None,
    aesgcm: Optional[AESGCM] = None,
) -> str:
    """
    Encrypt arbitrarily large strings using hybrid RSA + AES-GCM.

    Parameters:
        public_key (rsa.RSAPublicKey): The RSA public key for encrypting the AES key.
        plaintext (str): The plaintext string to encrypt.
        aes_key (Optional[bytes]): Existing AES key to reuse.
        aesgcm (Optional[AESGCM]): Existing AESGCM instance to reuse.

    Returns:
        str: The encrypted data, represented as a hex string (safe for DB text columns).
    """

    if aes_key is None:
        aes_key = AESGCM.generate_key(bit_length=256)
    if aesgcm is None:
        aesgcm = AESGCM(aes_key)

    nonce = os.urandom(12)
    plaintext_bytes = (
        plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    )
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    encrypted_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    return (encrypted_key + nonce + ciphertext).hex()


def decrypt_string(
    private_key: rsa.RSAPrivateKey,
    blob: str,
) -> str:
    """
    Decrypt data encrypted by encrypt_string().

    Parameters:
        private_key (rsa.RSAPrivateKey): The RSA private key for decrypting the AES key.
        blob (str): The encrypted data as a hex string.

    Returns:
        str: The decrypted plaintext string.
    """

    blob_bytes = bytes.fromhex(blob) if isinstance(blob, str) else blob
    rsa_key_size_bytes = private_key.key_size // 8

    encrypted_key = blob_bytes[:rsa_key_size_bytes]
    nonce = blob_bytes[rsa_key_size_bytes : rsa_key_size_bytes + 12]
    ciphertext = blob_bytes[rsa_key_size_bytes + 12 :]

    aes_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    plaintext = AESGCM(aes_key).decrypt(nonce, ciphertext, None)

    return plaintext.decode("utf-8")


def encrypt_data_to_file(
    public_key: rsa.RSAPublicKey,
    input_bytes: bytes,
    output_filepath: str,
    chunk_size: int = 1024 * 1024,
) -> None:
    """
    Split a buffer into chunks and encrypt each chunk using encrypt_string().

    Parameters:
        public_key (rsa.RSAPublicKey): The RSA public key for encrypting the AES key.
        input_bytes (bytes): The binary data to encrypt.
        output_filepath (str): The path to the output encrypted file.
        chunk_size (int): The size of each chunk in bytes. Default is 1MB.

    Returns:
        None
    """

    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    input_len = len(input_bytes)

    with open(output_filepath, "wb") as fout:
        fout.write(struct.pack(">Q", input_len))

        for i in range(0, input_len, chunk_size):
            chunk = input_bytes[i : i + chunk_size]
            encrypted_text = encrypt_string(public_key, chunk.hex(), aes_key, aesgcm)
            encoded = encrypted_text.encode("utf-8")
            fout.write(struct.pack(">I", len(encoded)))
            fout.write(encoded)


async def encrypt_stream_to_file(
    public_key: rsa.RSAPublicKey,
    reader: AsyncReader,
    output_filepath: str,
    chunk_size: int = 1024 * 1024,
) -> int:
    """
    Stream-encrypt data from an async reader to a file. Uses bounded memory:
    one chunk at a time, never holding the whole input. Produces a file in the
    same format as encrypt_data_to_file() so decrypt_data_from_file() works
    unchanged.

    The original size header is written as a placeholder up front, then
    overwritten with the true total after streaming completes.

    Parameters:
        public_key (rsa.RSAPublicKey): The RSA public key for the AES key wrap.
        reader (AsyncReader): Any object with `async read(size) -> bytes`.
        output_filepath (str): Destination path for the encrypted file.
        chunk_size (int): Plaintext chunk size in bytes (default 1 MB).

    Returns:
        int: total plaintext bytes encrypted.
    """

    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    total = 0

    async with aiofiles.open(output_filepath, "wb") as fout:
        # Placeholder for the u64 original-size header; rewritten at the end.
        await fout.write(struct.pack(">Q", 0))

        while True:
            chunk = await reader.read(chunk_size)
            if not chunk:
                break

            encrypted_text = await asyncio.to_thread(
                encrypt_string, public_key, chunk.hex(), aes_key, aesgcm
            )
            encoded = encrypted_text.encode("utf-8")

            await fout.write(struct.pack(">I", len(encoded)))
            await fout.write(encoded)
            total += len(chunk)

        await fout.seek(0)
        await fout.write(struct.pack(">Q", total))

    return total


def decrypt_data_from_file(
    private_key: rsa.RSAPrivateKey,
    input_filepath: str,
    start_chunk: int = 0,
    end_chunk: Optional[int] = None,
) -> Iterator[bytes]:
    """
    Decrypt a file encrypted by encrypt_data_to_file().
    Yields binary chunks.
    """

    chunk_index = 0

    with open(input_filepath, "rb") as fin:
        fin.read(8)

        # Skip to start_chunk more efficiently
        while chunk_index < start_chunk:
            length_bytes = fin.read(4)
            if not length_bytes:
                return  # File doesn't have enough chunks
            
            (chunk_length,) = struct.unpack(">I", length_bytes)
            fin.seek(chunk_length, 1)  # Seek forward instead of reading
            chunk_index += 1

        # Now decrypt and yield chunks from start_chunk to end_chunk
        while True:
            length_bytes = fin.read(4)
            if not length_bytes:
                break

            (chunk_length,) = struct.unpack(">I", length_bytes)
            encrypted_chunk = fin.read(chunk_length)
            if len(encrypted_chunk) != chunk_length:
                raise ValueError("Unexpected end of file while reading encrypted chunk")

            if end_chunk is not None and chunk_index > end_chunk:
                break

            encrypted_text = encrypted_chunk.decode("utf-8")
            decrypted_hex = decrypt_string(private_key, encrypted_text)
            yield bytes.fromhex(decrypted_hex)

            chunk_index += 1


def get_encrypted_file_size(
    input_filepath: str,
) -> int:
    """
    Get the original file size stored in an encrypted file.

    Parameters:
        input_filepath (str): The path to the encrypted file.

    Returns:
        int: The original file size in bytes.
    """

    with open(input_filepath, "rb") as fin:
        length_bytes = fin.read(8)

        if len(length_bytes) != 8:
            raise ValueError("Unexpected end of file while reading original file size")

        return struct.unpack(">Q", length_bytes)[0]


def get_encrypted_file_actual_size(
    input_filepath: str,
    chunk_size: int,
) -> int:
    """
    Get the actual available data size based on chunks present in the encrypted file.
    This may differ from the declared original size if the file is incomplete.

    Parameters:
        input_filepath (str): The path to the encrypted file.
        chunk_size (int): The size of each decrypted chunk.

    Returns:
        int: The actual available data size in bytes.
    """

    with open(input_filepath, "rb") as fin:
        original_size_bytes = fin.read(8)
        if len(original_size_bytes) != 8:
            return 0
        
        original_size = struct.unpack(">Q", original_size_bytes)[0]
        
        chunk_count = 0
        while True:
            length_bytes = fin.read(4)
            if not length_bytes:
                break
            
            (chunk_length,) = struct.unpack(">I", length_bytes)
            fin.seek(chunk_length, 1)
            chunk_count += 1
        
        # Calculate actual available size
        if chunk_count == 0:
            return 0
        
        # Calculate expected total chunks for the original size
        expected_total_chunks = (original_size + chunk_size - 1) // chunk_size
        
        if chunk_count >= expected_total_chunks:
            # File is complete
            return original_size
        else:
            # File is incomplete - calculate size based on what we have
            # All complete chunks are full size
            complete_chunks = chunk_count - 1
            
            # The last chunk size depends on the original file size
            # We know where the last chunk would fall in the original file
            last_chunk_original_offset = complete_chunks * chunk_size
            if last_chunk_original_offset >= original_size:
                # We only have complete chunks
                return complete_chunks * chunk_size
            else:
                # Calculate what the last chunk's size should be
                remaining_bytes = min(chunk_size, original_size - last_chunk_original_offset)
                return complete_chunks * chunk_size + remaining_bytes
