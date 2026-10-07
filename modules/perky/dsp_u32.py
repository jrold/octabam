"""Perky DSP source emitter for exact ARM-shaped low32 arithmetic.

Values are two unsigned16 limbs; operations preserve modulo-2^32 results,
signed comparisons/shifts, and accumulator extension/fractional semantics.
Scratch helpers use r5, persistent state uses r6, variables use r4. Recipes
supply their own table access, control law, entry ABI and physical allocation.
"""

class Emitter:
    def __init__(self):
        self.lines = []
        self.variables = {}
        self.sequence = 0

    def emit(self, *lines):
        self.lines.extend('        ' + line for line in lines)

    def label(self):
        self.sequence += 1
        return f'pkr_label_{self.sequence:05d}'

    def mark(self, label):
        self.lines.append(label + ':')

    def var(self, name):
        if name not in self.variables:
            self.variables[name] = ('r4', 2 * len(self.variables), 32)
        return self.variables[name]

    def state(self, offset, width=32):
        return ('r6', offset, width)

    @staticmethod
    def addr(value, limb=0):
        return f'x:({value[0]}+${value[1] + limb:x})'

    def limbs(self, value, low, high):
        if isinstance(value, int):
            self.emit(f'move #>${value & 65535:06x},a', f'move a1,{low}',
                      f'move #>${(value >> 16) & 65535:06x},a', f'move a1,{high}')
        else:
            self.emit(f'move {self.addr(value)},a', f'move a1,{low}')
            if value[2] == 32:
                self.emit(f'move {self.addr(value, 1)},a')
            else:
                self.emit('clr a')
            self.emit(f'move a1,{high}')

    def assign(self, dst, value):
        self.limbs(value, self.addr(dst), self.addr(dst, 1) if dst[2] == 32 else 'x:(r5+$13)')
        return dst

    def load(self, value, signed=True):
        # A contains the signed/unsigned 32-bit operand aligned by eight bits.
        if isinstance(value, int):
            high = (value >> 16) & 65535
            if signed and high & 32768:
                high -= 65536
            self.emit(f'move #>${high & 0xFFFFFF:06x},a', f'move #>${(value & 65535) << 8:06x},a0')
        elif value[2] == 16:
            self.emit('clr a', f'move {self.addr(value)},b', 'lsl #$8,b', 'move b1,a0')
        else:
            self.emit(f'move {self.addr(value, 1)},a')
            if signed:
                self.emit('asl #$8,a,a', 'move a1,a', 'asr #$8,a,a')
            self.emit(f'move {self.addr(value)},b', 'lsl #$8,b', 'move b1,a0')

    def save(self, dst):
        if dst[2] == 32:
            self.emit('move a1,b', 'and #>$00ffff,b', f'move b1,{self.addr(dst, 1)}')
        self.emit('move a0,b', 'lsr #$8,b', 'and #>$00ffff,b', f'move b1,{self.addr(dst)}')
        return dst

    def compare(self, left, right, branch, label, signed=True):
        self.load(right, signed)
        self.emit('move a1,x1', 'move a0,y1')
        self.load(left, signed)
        self.emit('move x1,b', 'move y1,b0', 'cmp b,a', f'{branch} {label}')

    def binary(self, dst, left, right, op):
        self.limbs(left, 'x:(r5+$0)', 'x:(r5+$1)')
        self.limbs(right, 'x:(r5+$2)', 'x:(r5+$3)')
        self.emit(f'jsr pk_u32_{op}')
        self.emit('move x:(r5+$8),a', f'move a1,{self.addr(dst)}')
        if dst[2] == 32:
            self.emit('move x:(r5+$9),a', f'move a1,{self.addr(dst, 1)}')
        return dst

    def arithmetic(self, dst, left, right, op):
        # Positive 32-bit operands aligned in 56 bits; save discards carry or
        # borrow above bit31. No accumulator-to-accumulator limiting move.
        self.load(right, signed=False)
        self.emit('move a1,x1', 'move a0,y1')
        self.load(left, signed=False)
        self.emit('move x1,b', 'move y1,b0', f'{op} b,a')
        return self.save(dst)

    def add(self, dst, a, b): return self.arithmetic(dst, a, b, 'add')
    def sub(self, dst, a, b): return self.arithmetic(dst, a, b, 'sub')
    def mul(self, dst, a, b): return self.binary(dst, a, b, 'mul_low')

    def shift(self, dst, value, amount, signed=True):
        self.load(value, signed)
        if isinstance(amount, int):
            self.emit(f'asr #>${amount:x},a,a')
        else:
            self.emit(f'move {self.addr(amount)},x0', 'asr x0,a,a')
        return self.save(dst)

    def left(self, dst, value, amount):
        self.load(value, signed=False)
        if isinstance(amount, int):
            self.emit(f'asl #>${amount:x},a,a')
        else:
            self.emit(f'move {self.addr(amount)},x0', 'asl x0,a,a')
        return self.save(dst)

    def bits(self, dst, left, right, op='and'):
        for limb in range(2 if dst[2] == 32 else 1):
            if isinstance(left, int):
                self.emit(f'move #>${(left >> (16 * limb)) & 65535:06x},a')
            elif limb and left[2] == 16:
                self.emit('clr a')
            else:
                self.emit(f'move {self.addr(left, limb)},a')
            if isinstance(right, int):
                self.emit(f'{op} #>${(right >> (16 * limb)) & 65535:06x},a')
            elif limb and right[2] == 16:
                if op == 'and': self.emit('clr a')
            else:
                self.emit(f'move {self.addr(right, limb)},x0', f'{op} x0,a')
            self.emit(f'move a1,{self.addr(dst, limb)}')
        return dst

    def clamp(self, dst, low=-32767, high=32767):
        okay_low, done = self.label(), self.label()
        self.compare(dst, low, 'bge', okay_low)
        self.assign(dst, low)
        self.mark(okay_low)
        self.compare(dst, high, 'ble', done)
        self.assign(dst, high)
        self.mark(done)

    def abs(self, dst, value):
        done = self.label()
        self.assign(dst, value)
        self.compare(dst, 0, 'bge', done)
        self.sub(dst, 0, dst)
        self.mark(done)

    def interpolation(self, dst, pitch, table):
        # phase = signed16(pitch) <<17 modulo32. Index/fraction are determined
        # by the raw low16 pitch, independent of its sign extension.
        self.emit(f'move {self.addr(pitch)},a', 'lsr #$7,a', 'and #>$0000ff,a',
                  'move a1,n1', f'move #>${table:06x},r1', 'lua (r1+n1),r2',
                  'move y:(r2),a', 'move a1,x:(r5+$7a)', 'move y:(r2+$1),b',
                  'sub a,b', 'move b1,x0', f'move {self.addr(pitch)},a',
                  'lsl #$9,a', 'and #>$00ffff,a', 'move a1,y0', 'mpy y0,x0,a',
                  'asr #$11,a,a', 'move a0,a', 'and #>$00ffff,a',
                  'move x:(r5+$7a),x0', 'add x0,a', 'and #>$00ffff,a',
                  f'move a1,{self.addr(dst)}', 'clr a', f'move a1,{self.addr(dst, 1)}')
