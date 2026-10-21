"""On-demand resident Hat checkpoint in reclaimed, unused A waveform Y.

The active Hat program reads curves at 09a5/c51 and its clock at f3f; the
legacy waveform region 07a5..09a5 is not read by the surviving program.
The direct paired DSP gate must prove this for every published candidate.
No transfer count, audio framing, source latency, or carrier width changes.
"""
import json
from pathlib import Path

BASE = 0x7A5
STATE_WORDS = 180
SIDE_WORDS = 6
CLOCK_WORDS = 3
STREAM_WORDS = 1 + STATE_WORDS + SIDE_WORDS + CLOCK_WORDS
CURSOR = BASE + STREAM_WORDS
BUFFER_END = CURSOR + 1
REQUEST_BIT = 11
REQUEST_MASK = 1 << REQUEST_BIT
MARKER = 0x8000
MAIL_WORDS = 24
RING_CAPACITY = 20


def initial_y_patch():
    """Initial table overwrite, applied after the retired waveform is loaded."""
    return [(BASE, [0] * STREAM_WORDS + [STREAM_WORDS])]


def snapshot_initial_y(words):
    """Return A's table payload with only the reclaimed waveform range changed."""
    words = list(words)
    for base, values in initial_y_patch():
        offset = base - 0x7A5
        assert 0 <= offset < offset + len(values) <= len(words)
        words[offset:offset + len(values)] = values
    return words


def contract():
    return dict(schema='perky.hat-state-dsp.v1', buffer_space='y',
                buffer_base=BASE, buffer_end=BUFFER_END, cursor_address=CURSOR,
                stream_words=STREAM_WORDS, request_segment_header_bit=REQUEST_BIT,
                order=[dict(name='sequence', offset=0, words=1, source='x:39f1'),
                       dict(name='compact', offset=1, words=180, source='x:3800'),
                       dict(name='side', offset=181, words=6, source='x:3970'),
                       dict(name='clock', offset=187, words=3, source='x:3a23')],
                mail=dict(words=MAIL_WORDS, ring_count_index=2,
                          marker_index=3, marker_bit=MARKER,
                          offset_mask=255, payload_start='4 + ring_count',
                          payload_count='min(20-ring_count,190-offset)'),
                reclaimed_Y=[BASE, BUFFER_END], retired_wave_Y=[0x7A5, 0x9A5],
                required_live_Y_bases=[0x9A5, 0xC51, 0xF3F],
                capture='whole source frame end, before register restore',
                cancel='epoch reset sets cursor to stream_words',
                limits=['Data reclaim requires actual-DSP poison/read-watch proof.',
                        'CF must bind full sequence and generation; 16-bit sequence alone is not a lifetime token.'])


def write_contract(work):
    path = Path(work) / 'STATE_HANDOFF_CONTRACT.json'
    path.write_text(json.dumps(contract(), indent=2) + '\n')
    return path


CAPTURE = f'''nhs_capture:
 move #>${BASE:x},r1
 move x:>$39f1,a
 move a1,y:(r1)+
 move #>$3800,r2
 do #>180,nhs_compact_copied
 move x:(r2)+,a
 move a1,y:(r1)+
nhs_compact_copied:
 nop
 move #>$3970,r2
 do #>6,nhs_side_copied
 move x:(r2)+,a
 move a1,y:(r1)+
nhs_side_copied:
 nop
 move #>$3a23,r2
 do #>3,nhs_clock_copied
 move x:(r2)+,a
 move a1,y:(r1)+
nhs_clock_copied:
 nop
 clr a
 move a1,y:(r1)
 rts
'''


STREAM = f'''nhs_send:
 clr a
 move a1,x:>$39f3
 move y:>${CURSOR:x},a
 cmp #>{STREAM_WORDS},a
 bge nhs_done_send
 move a1,n1
 move #>${BASE:x},r1
 move (r1)+n1
 move x:>$39f2,a
 cmp #>20,a
 bge nhs_done_send
 move a1,n2
 move #>$39f4,r2
 move (r2)+n2
 move #>20,b
 sub a,b
 move #>{STREAM_WORDS},a
 move n1,x0
 sub x0,a
 move a1,x0
 cmp x0,b
 ble nhs_count_ready
 move x0,b
nhs_count_ready:
 move n1,a
 or #>${MARKER:x},a
 move a1,x:>$39f3
 do b,nhs_payload_copied
 move y:(r1)+,a
 move a1,x:(r2)+
nhs_payload_copied:
 nop
 move r1,a
 sub #>${BASE:x},a
 move a1,y:>${CURSOR:x}
nhs_done_send:
 rts
'''


def transform(parts):
    """Transform the final full-map DSP service dictionary before assembly."""
    parts = dict(parts)
    marker = ' move a1,x:>$39f2\n move #>1,a\n'
    assert parts['frame'].count(marker) == 1
    parts['frame'] = parts['frame'].replace(marker, f''' move a1,x:>$39f2
 move x:>$39b9,a
 jclr #{REQUEST_BIT},a1,nhs_no_capture
 jsrl nhs_capture
nhs_no_capture:
 jsrl nhs_send
 move #>1,a
''')
    marker = 'nhg_epoch_reset:\n'
    assert parts['epoch_reset'].count(marker) == 1
    parts['epoch_reset'] = parts['epoch_reset'].replace(marker, marker + f''' move #>{STREAM_WORDS},a
 move a1,y:>${CURSOR:x}
''')
    parts['state_capture'] = CAPTURE
    parts['state_stream'] = STREAM
    return parts
