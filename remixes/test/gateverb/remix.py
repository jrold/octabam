"""Minimal image for GATE VERB's gate: the module alone, no stock effect listed."""
from remix.schema import Proof, Remix
REMIX = Remix(family="effects", proof=Proof.RENDER, proof_note="`verify_gateverb`; not flashed", name="gateverb",
              doc="GATE VERB alone: the fixture of its render gate.",
              modules=("GATE VERB",), fallback="NONE")
