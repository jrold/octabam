// Sweep one PĒRKONS panel control through the real firmware and dump the
// engine's wrapper window for every position.
//
//   capture_sweep <firmware> <out-file> <engine-index 0..11> <panel-mode 0..2>
//                 [sweep|traj|full] [note]
//
// One record per (control, value): control 0..3 with the other three held at
// the mid panel position, value 0..127 mapped through the same 7-bit -> 12-bit
// panel target law the shipping control path uses (v == 127 -> 4095, else
// v << 5).  The record is the 0x6000-byte wrapper window, so the caller can
// slice any engine object out of it and read the derived fields.
//
// This is the missing half for every family whose update path was never
// translated: three control corners can check a law, 128 points can recover it.
//
// [note] overrides the played note (default 63, the engine-default).  The
// control laws derive the raw pitch index from
//     ix = clamp12(prep_tune - 0x800 + note_offset(note))
// so a family whose captures use a different note -- or whose whole raw-pitch
// range has to be walked -- needs its own note.  Acoustic Hats' sample-playback
// increment is a table over ix that no closed form matched, and note 45 (the
// shipping note) puts ix = prep, i.e. the complete 0..4095 domain.
#include "EngineCatalog.h"
#include "FirmwareImage.h"
#include "PerkonsM7.h"
#include "PerkonsVoices.h"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

const std::uint32_t kWrappers[] = {0x20000280u, 0x200006d4u, 0x20003930u, 0x20000b58u};
constexpr std::size_t kWindow = 0x6000u;

std::uint16_t panel_target(unsigned value)
{
    return value >= 127u ? 4095u : static_cast<std::uint16_t>(value << 5);
}

}  // namespace

int main(int argc, char** argv)
{
    if (argc < 5 || argc > 7) {
        std::cerr << "usage: capture_sweep <firmware> <out-file> <engine 0..11> <panel-mode 0..2> [sweep|traj|full] [note]\n";
        return 2;
    }
    FirmwareImage fw;
    std::string error;
    if (!fw.load(argv[1], error)) {
        std::cerr << error;
        return 3;
    }
    const unsigned index = std::strtoul(argv[3], nullptr, 0);
    const unsigned mode = std::strtoul(argv[4], nullptr, 0);
    const bool traj = argc >= 6 && std::string(argv[5]) == "traj";
    const bool full = argc >= 6 && std::string(argv[5]) == "full";
    const unsigned note = argc == 7 ? std::strtoul(argv[6], nullptr, 0) : 0u;
    if (index >= kPerkyEngines.size() || mode > 2u) return 4;

    std::ofstream out(argv[2], std::ios::binary);
    if (!out) return 5;

    const auto& engine = kPerkyEngines[index];
    const std::uint32_t wrapper = kWrappers[static_cast<unsigned>(engine.slot)];
    std::vector<std::uint8_t> ram(kWindow);

    // A non-zero [note] sets the played note AND plays it after the controls
    // settle: the note only reaches the object through a trigger, and the
    // update derives the raw pitch index from the object's own note byte.
    const auto tune = [&](PerkonsVoices& voices) {
        return note == 0u
            || voices.setNote(engine.slot, static_cast<std::uint8_t>(note), error);
    };
    const auto play = [&](PerkonsVoices& voices) {
        return note == 0u || voices.trigger(engine.slot, error);
    };

    if (traj) {
        // Dense map from the SMOOTHED control word to the derived fields: set
        // the targets without settling, then step the firmware's own update
        // pass one at a time and capture the object after each step.  The
        // converged sweep above only exercises the settled words, which leaves
        // the law's behaviour between them undetermined.
        constexpr unsigned kSteps = 24u;
        for (unsigned value = 0; value < 128u; ++value) {
            PerkonsM7 cpu;
            PerkonsVoices voices(cpu);
            std::array<std::uint16_t, 4> values = {panel_target(value), panel_target(value),
                                                   panel_target(value), panel_target(value)};
            if (!cpu.load(fw, error) || !voices.initialise(fw, error)
                || !voices.setAlgorithm(engine.slot, engine.panelAlgorithm, error)
                || !tune(voices)
                || !voices.setMode(engine.slot, engine.panelModeToFirmware[mode], error)
                || !voices.setSoundParameters(engine.slot, values, error, 0u)
                || !play(voices)) {
                std::cerr << error;
                return 6;
            }
            for (unsigned step = 0; step < kSteps; ++step) {
                if (!voices.advanceControlSmoothing(engine.slot, error, 1u)
                    || !cpu.readMemory(wrapper, ram.data(), ram.size(), error)) {
                    std::cerr << error;
                    return 6;
                }
                out.write(reinterpret_cast<const char*>(ram.data()),
                          static_cast<std::streamsize>(ram.size()));
            }
        }
        std::cout << "trajectory engine " << index + 1 << " mode " << mode + 1
                  << ": " << (128u * kSteps) << " windows -> " << argv[2] << '\n';
        return 0;
    }

    if (full) {
        // Every 12-bit target, fully settled: the derived field for each
        // reachable prepared word with no 7-bit quantisation gaps.  Needed for a
        // law whose step pattern is not resolvable on the 128-point grid.
        for (unsigned value = 0; value < 4096u; ++value) {
            PerkonsM7 cpu;
            PerkonsVoices voices(cpu);
            std::array<std::uint16_t, 4> values = {
                static_cast<std::uint16_t>(value), static_cast<std::uint16_t>(value),
                static_cast<std::uint16_t>(value), static_cast<std::uint16_t>(value)};
            if (!cpu.load(fw, error) || !voices.initialise(fw, error)
                || !voices.setAlgorithm(engine.slot, engine.panelAlgorithm, error)
                || !tune(voices)
                || !voices.setMode(engine.slot, engine.panelModeToFirmware[mode], error)
                || !voices.setSoundParameters(engine.slot, values, error)
                || !play(voices)
                || !cpu.readMemory(wrapper, ram.data(), ram.size(), error)) {
                std::cerr << error;
                return 6;
            }
            out.write(reinterpret_cast<const char*>(ram.data()),
                      static_cast<std::streamsize>(ram.size()));
        }
        std::cout << "full target sweep engine " << index + 1 << " mode " << mode + 1
                  << ": 4096 windows -> " << argv[2] << '\n';
        return 0;
    }

    for (unsigned control = 0; control < 4u; ++control) {
        for (unsigned value = 0; value < 128u; ++value) {
            PerkonsM7 cpu;
            PerkonsVoices voices(cpu);
            std::array<std::uint16_t, 4> values = {2048u, 2048u, 2048u, 2048u};
            values[control] = panel_target(value);
            if (!cpu.load(fw, error) || !voices.initialise(fw, error)
                || !voices.setAlgorithm(engine.slot, engine.panelAlgorithm, error)
                || !tune(voices)
                || !voices.setMode(engine.slot, engine.panelModeToFirmware[mode], error)
                || !voices.setSoundParameters(engine.slot, values, error)
                || !play(voices)
                || !cpu.readMemory(wrapper, ram.data(), ram.size(), error)) {
                std::cerr << error;
                return 6;
            }
            out.write(reinterpret_cast<const char*>(ram.data()),
                      static_cast<std::streamsize>(ram.size()));
        }
    }
    std::cout << "swept engine " << index + 1 << " mode " << mode + 1
              << ": " << (4u * 128u) << " windows -> " << argv[2] << '\n';
    return 0;
}
