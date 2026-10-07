"""Lossless bounded second-difference blocks for original wavetable assets.

Per asset: one signed first-difference width, one descriptor per 32 samples,
word-aligned blocks, final adjacent-read guard. Descriptor packs a 19-bit word
offset and 5-bit signed second-difference width. This is a storage ABI; DSP
execution and physical placement are separate gates.
"""
from dataclasses import dataclass


def signed_width(value):
    return max(1, (value if value >= 0 else ~value).bit_length() + 1)


@dataclass(frozen=True)
class WaveAsset:
    first_width: int
    descriptors: tuple[int, ...]
    data: tuple[int, ...]
    samples: int
    block: int = 32

    @property
    def words(self):
        return (self.first_width, *self.descriptors, *self.data)

    def decode_block(self, index):
        descriptor = self.descriptors[index]
        width = descriptor >> 19
        offset = descriptor & 0x7ffff
        cursor = 0
        def read(bits):
            nonlocal cursor
            at, shift = divmod(cursor, 24)
            value = ((self.data[offset + at] | self.data[offset + at + 1] << 24)
                     >> shift) & ((1 << bits) - 1)
            cursor += bits
            return value - (1 << bits) if value & (1 << (bits - 1)) else value
        value = read(16)
        delta = read(self.first_width)
        result = [value, value + delta]
        value += delta
        for _ in range(self.block - 2):
            delta += read(width)
            value += delta
            assert -32768 <= value <= 32767
            result.append(value)
        return tuple(result)

    def sample(self, index):
        if not 0 <= index < self.samples:
            raise IndexError(index)
        return self.decode_block(index // self.block)[index % self.block]


def pack(samples, block=32):
    values = tuple(samples)
    if block not in (16, 32, 64) or not values or any(not -32768 <= v <= 32767 for v in values):
        raise ValueError('signed16 samples and a 16/32/64-sample block are required')
    blocks = []
    for at in range(0, len(values), block):
        chunk = list(values[at:at + block])
        chunk += [chunk[-1]] * (block - len(chunk))
        blocks.append(chunk)
    first_width = max(signed_width(v[1] - v[0]) for v in blocks)
    descriptors, words = [], []
    for chunk in blocks:
        differences = [chunk[i] - chunk[i - 1] for i in range(1, block)]
        seconds = [differences[i] - differences[i - 1] for i in range(1, block - 1)]
        width = max(map(signed_width, seconds))
        assert width <= 18 and first_width <= 17 and len(words) < 1 << 19
        descriptors.append((width << 19) | len(words))
        bits, count = 0, 0
        for value, size in [(chunk[0], 16), (differences[0], first_width), *[(v, width) for v in seconds]]:
            bits |= (value & ((1 << size) - 1)) << count
            count += size
            while count >= 24:
                words.append(bits & 0xffffff)
                bits >>= 24
                count -= 24
        if count:
            words.append(bits)
    words.append(0)
    asset = WaveAsset(first_width, tuple(descriptors), tuple(words), len(values), block)
    actual = tuple(v for i in range(len(blocks)) for v in asset.decode_block(i))[:len(values)]
    assert actual == values
    return asset
