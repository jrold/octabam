"""PERKY Noise/Tone full machine development canary.

The build wrapper upgrades the tracked PERKY PROBE module in memory only with
machine.s, generated control.s and the complete packed Noise/Tone DSP source.
PLATE/SPRING/DARK/COMPRESSOR/LO-FI are omitted so the correctness-first renderer
owns their contiguous donor P region ($1000..$1d70 = 3,441 words). The tracked
impulse probe remains unchanged.

COMPRESSOR and LO-FI were added to that set for Fold Drum 2: Fold2 costs 279 P
words marginal (2,680 -> 2,959 composed), COMPRESSOR alone lands at 2,904 -- 55
short -- and the remaining 41 could not come from deduplication (the composed
source has 179 labels, all unique). See modules/perky/STEP2_FOLD2_INTEGRATION.md.
"""
from remix.schema import Proof, Remix

REMIX = Remix(
    name="perky-machine",
    family="probes",
    proof=Proof.CHECK,
    proof_note="development full PERKY machine; emulator/hardware qualification pending",
    doc=(
        "Full PERKY source-machine canary: chooser/signature/UI/control runtime "
        "plus packed DSP renderer; five stock effects intentionally omitted "
        "(PLATE/SPRING/DARK/COMPRESSOR/LO-FI)."
    ),
    modules=(
        "PERKY PROBE",
        "FILTER", "EQUALIZER", "DJ EQ", "PHASER", "FLANGER", "CHORUS",
        "SPATIALIZER", "COMB FILTER", "DELAY",
    ),
    # THE CHOPPERS ARE WHAT RELEASES P WORDS, NOT THE MODULE LIST ABOVE.
    # `stock.harvested()` is "stock effects with DSP code that are on NEITHER chooser",
    # so a module omitted from `modules` but still on a chooser keeps its algorithm and
    # its P words -- which is exactly what happened for two rounds: PERKY4's region stayed
    # at 2,724 words (the three reverbs) because COMPRESSOR and LO-FI were still listed on
    # the stock choosers, and an empty fx1 means "stock chooser". perky-hw4's remix says so
    # outright -- "The explicit FX1 list matters: leaving it empty means 'stock FX1
    # chooser', which would keep the omitted stock effects alive and therefore make their
    # P code unharvestable." This is that fix applied here.
    #
    # `fx1` is the ONE list the schema has, and it governs either chooser (perky-hw4:
    # "FILTER is the only stock DSP insert retained on either chooser"). So it holds every
    # stock DSP insert we keep, which is the union of both stock choosers
    # (FX1_CHOOSER 0x400d6060, FX2_CHOOSER 0x400d6090) MINUS COMPRESSOR (fx2 id 24) and
    # LO-FI (28) -- those two sit on BOTH choosers, and an fx2 id is also an fx1 id, so
    # both must release them. That frees the contiguous run
    # PLATE 0x1000 + SPRING 0x1252 + DARK 0x1679 + COMPRESSOR 0x1aa4 + LO-FI 0x1b58
    # = 3,441 words, which is what Fold Drum 2 needs (2,959).
    # DELAY is deliberately absent: stock lists it on FX2 only, "because it does not fit
    # a 3,072-word FX1 allocation", and the build refuses an fx1 that names it. It is kept
    # on FX2 by `modules` above, which is where it belongs.
    fx1=(
        "FILTER", "SPATIALIZER", "EQUALIZER", "DJ EQ", "PHASER",
        "FLANGER", "CHORUS", "COMB FILTER",
    ),
    fallback="NONE",
)
