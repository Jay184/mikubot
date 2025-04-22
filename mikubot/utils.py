import base64
import lzma


def decode_lzma_base64(encoded_str, *, encoding: str = 'utf-8'):
    compressed_data = base64.b64decode(encoded_str)
    decompressed_data = lzma.decompress(compressed_data)
    return decompressed_data.decode(encoding)


def encode_lzma_base64(input_str, *, encoding: str = 'utf-8'):
    compressed_data = lzma.compress(input_str.encode(encoding))
    encoded_str = base64.b64encode(compressed_data)
    return encoded_str.decode(encoding)
