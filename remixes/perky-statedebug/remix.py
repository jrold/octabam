"""MINIMAL PERKY HOOK DEBUG -- the hardware-blocker bisect, part one.

WHY THIS EXISTS. On the physical Octatrack, with a Perky machine assigned,
pressing PLAY while the sequencer was running stopped the sequencer advancing,
and STOP/PLAY left it stuck on step 1. The production hook ended its
not-admitted path with `rts`, but the hook site is STRAIGHT-LINE stock code
reached by fall-through -- nothing called it -- so the `rts` popped a return
address that was never ours and the DSP left for hyperspace. The frame never
completed, the ColdFire waited for a handshake that never arrived, and the
sequencer stopped. Every track that was not the admitted one took that path.

This remix carries the FIX and nothing else: the source hook, its site, its
admission test and its two continuations. NO renderer, no audio, no ColdFire
side, no Y tables, no Perky machine on any track.

FLASH IT INSTEAD OF ANOTHER PERKY IMAGE, AND READ THE RESULT:

  * sequencer runs normally, Perky track silent, other tracks unaffected
      -> the hook mechanism, both continuation addresses and the admission test
         are sound. The wedge was the `rts`, and the next debug target is the
         hook PLUS a renderer that renders but writes nothing.

  * sequencer STILL stops
      -> the fault is in the hook MECHANISM: the patch at the site, the
         placement, the displaced-instruction replay, or an address the build
         bound. The renderer is NOT implicated and must not be touched until
         this is understood.

Either outcome is a result. Neither is a shipping image.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-statedebug",
    family="probes",
    proof=Proof.CHECK,
    proof_note="minimal source-hook debug insert: admission + both "
               "continuations, no renderer",
    doc=("Source-hook debug insert for the hardware wedge. Renders nothing. "
         "Flash this before any further Perky image."),
    modules=("PERKY STATEDBG",),
    # NO extra effects are given up: the insert is tiny and carries no tables.
    fx1=(),
    fallback="NONE",
)
