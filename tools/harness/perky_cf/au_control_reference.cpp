// Independent public-control path through the user's local PerkyBits runtime.
// Args: firmware panel_mode tune decay par1 par2 output native_enabled [MIDI.tsv]
// MIDI.tsv: absolute sample, status byte, data1, data2 (all decimal).
#include "EngineCatalog.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <vector>
struct Event { unsigned sample, status, data1, data2; };
int main(int argc, char** a) {
    if (argc != 9 && argc != 10) return 2;
    FirmwareImage fw; PerkonsM7 cpu; PerkonsVoices voices(cpu); std::string error;
    auto check = [&](bool success) { if (!success) { std::cerr << error; std::exit(3); } };
    check(fw.load(a[1], error)); check(cpu.load(fw, error)); check(voices.initialise(fw, error));
    const auto slot = PerkonsVoices::Slot::voice2;
    int mode = std::stoi(a[2]); if (mode < 0 || mode > 2) return 2;
    check(voices.setAlgorithm(slot, 2, error));
    check(voices.setMode(slot, std::array<unsigned char, 3>{1, 0, 2}[mode], error));
    std::array<unsigned short, 4> params;
    for (int i = 0; i < 4; ++i) params[i] = std::stoi(a[i + 3]);
    check(voices.setSoundParameters(slot, params, error, 16));
    check(voices.setVelocity(slot, 255, error)); check(voices.setNote(slot, 45, error));
    check(voices.trigger(slot, error));
    std::vector<unsigned char> state(0x140);
    check(cpu.readMemory(0x200006d4 + 0x1f8, state.data(), state.size(), error));
    std::ofstream snapshot(std::string(a[7]) + ".state", std::ios::binary);
    snapshot.write(reinterpret_cast<char*>(state.data()), state.size());
    std::vector<Event> events;
    if (argc == 10) {
        std::ifstream input(a[9]); Event event;
        if (!input) return 4;
        while (input >> event.sample >> event.status >> event.data1 >> event.data2) events.push_back(event);
        if (!input.eof() || !std::is_sorted(events.begin(), events.end(), [](auto x, auto y){return x.sample < y.sample;})) return 4;
    }
    std::ofstream output(a[7], std::ios::binary);
    voices.setNativeDspEnabledForTesting(std::stoi(a[8]) != 0);
    unsigned pending = 0; size_t next = 0; short pcm[256];
    for (unsigned at = 0; at < 192000; at += 256) {
        bool updated = false; unsigned cursor = at;
        auto render = [&](unsigned count) {
            if (!count) return;
            check(pending && !updated ? voices.renderIntoAfterControlUpdate(slot, pcm, count, error)
                                     : voices.renderInto(slot, pcm, count, error));
            if (pending && !updated) { --pending; updated = true; }
            output.write(reinterpret_cast<char*>(pcm), count * sizeof(short));
        };
        while (next < events.size() && events[next].sample < at + 256) {
            auto ev = events[next++]; render(ev.sample - cursor); cursor = ev.sample;
            if (ev.status == 144) {
                check(voices.setVelocity(slot, std::lround(ev.data2 * 255.0 / 127), error));
                check(voices.setNote(slot, 45, error)); check(voices.trigger(slot, error));
            } else if (ev.status == 128) check(voices.release(slot, error));
            else if (ev.status == 176 && ev.data1 >= 20 && ev.data1 <= 23) {
                params[ev.data1 - 20] = std::lround(ev.data2 * 4095.0 / 127);
                check(voices.setSoundParameters(slot, params, error, 0)); pending = 16;
            } else return 4;
        }
        render(at + 256 - cursor);
    }
    return output && snapshot ? 0 : 4;
}
