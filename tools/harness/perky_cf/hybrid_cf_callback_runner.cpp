#include "machine.h"
#include "hybrid_cf_alignment.hpp"
#include "mc68k/Musashi/m68k.h"
#include "mc68k/cpuState.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

static std::vector<uint8_t> read(const std::string &path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("read " + path);
    return {std::istreambuf_iterator<char>(input), {}};
}

struct Cost { uint64_t cycles, instructions; uint32_t stack; };
static Cost call(ot::Machine &machine, uint32_t pc)
{
    HybridAlignmentScope alignment_scope;
    constexpr uint32_t stack = 0x47100000, sentinel = 0x47200000;
    m68k_set_reg(machine.getCpuState(), M68K_REG_SR, 0x2700);
    m68k_set_reg(machine.getCpuState(), M68K_REG_SP, stack);
    m68k_set_reg(machine.getCpuState(), M68K_REG_PC, pc);
    machine.write32(stack, sentinel);
    const auto before = machine.getCycles();
    uint64_t instructions = 0;
    uint32_t low = stack;
    while (machine.pcFast() != sentinel) {
        if (++instructions > 100000000 || !machine.stepFast())
            throw std::runtime_error("callback stopped: " + machine.why());
        low = std::min(low, m68k_get_reg(machine.getCpuState(), M68K_REG_SP));
    }
    if (machine.getCycles() < before ||
        m68k_get_reg(machine.getCpuState(), M68K_REG_SP) != stack + 4)
        throw std::runtime_error("callback cycle/stack ABI");
    return {machine.getCycles() - before, instructions, stack - low};
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    const std::string output = argv[1], assets = argv[2];
    std::map<std::string, uint32_t> symbols;
    std::ifstream nm(output + "/callback.nm");
    std::string line;
    while (std::getline(nm, line)) {
        std::istringstream fields(line);
        uint32_t address;
        char type;
        std::string name;
        if (fields >> std::hex >> address >> type >> name) symbols[name] = address;
    }
    for (const auto *name : {"bench_callback_pcm", "pk_final_pcm_cookie",
            "pk_pcm_wt_base", "pk_pcm_wt_bank", "pk_asset_pcm_rice",
            "pk_asset_pcm_rice_end", "__bss_start", "__bss_end"})
        if (!symbols.count(name)) throw std::runtime_error(std::string("symbol ") + name);
    const auto bss_start = symbols.at("__bss_start"), bss_end = symbols.at("__bss_end");
    if (bss_end - bss_start != 200704)
        throw std::runtime_error("unexpected retained callback BSS extent");
    ot::Machine machine(read(output + "/callback.bin"));
    HybridAlignment alignment(machine); hybrid_alignment=&alignment;
    constexpr uint32_t cold = 0x504b5043, ready = 0x504b5052;
    const auto cookie = symbols.at("pk_final_pcm_cookie");
    if (cookie >= bss_start || machine.read32(cookie) != cold)
        throw std::runtime_error("shipping PCM cookie was not loaded COLD outside BSS");
    for (uint32_t address = bss_start; address < bss_end; ++address)
        machine.write8(address, uint8_t((address * 37 + 0xa5) & 255));
    uint64_t packed_reads = 0, destination_writes = 0;
    machine.addReadWatch(symbols.at("pk_asset_pcm_rice"),
        symbols.at("pk_asset_pcm_rice_end") - 1,
        [&](uint32_t, uint8_t, uint32_t, uint32_t) { ++packed_reads; });
    machine.addWriteWatch(bss_start, bss_end - 1,
        [&](uint32_t, uint8_t, uint32_t, uint32_t) { ++destination_writes; });
    // A partial or empty asset set must never mark the actual shipping cookie
    // READY. Test before the first valid decode while all destinations remain
    // poisoned. Reuse the same machine so failure cannot hide behind a reset.
    std::ostringstream rejected_counts;
    bool first_rejected = true;
    for (const uint32_t count : {0u, 1u, 3u}) {
        const auto header = symbols.at("pk_asset_pcm_rice") + 4;
        for (unsigned byte = 0; byte < 4; ++byte)
            machine.write8(header + byte, uint8_t(count >> (8 * byte)));
        packed_reads = destination_writes = 0;
        const auto rejected = call(machine, symbols.at("bench_callback_pcm"));
        if (m68k_get_reg(machine.getCpuState(), M68K_REG_D0) != 0 ||
            machine.read32(cookie) != cold || destination_writes)
            throw std::runtime_error("malformed asset count reached READY or changed PCM");
        if (!first_rejected) rejected_counts << ',';
        first_rejected = false;
        rejected_counts << "{\"asset_count\":" << count
                        << ",\"return_value\":0,\"cookie_stayed_cold\":true"
                        << ",\"destination_writes\":" << destination_writes
                        << ",\"packed_reads\":" << packed_reads
                        << ",\"stack_bytes\":" << rejected.stack
                        << ",\"cycles\":" << rejected.cycles << '}';
    }
    const auto original_stream = read(output + "/packed.pkr");
    for (unsigned byte = 4; byte < 8; ++byte)
        machine.write8(symbols.at("pk_asset_pcm_rice") + byte, original_stream.at(byte));
    packed_reads = destination_writes = 0;
    const auto initial = call(machine, symbols.at("bench_callback_pcm"));
    if (m68k_get_reg(machine.getCpuState(), M68K_REG_D0) != 1 ||
        machine.read32(cookie) != ready)
        throw std::runtime_error("shipping guard did not decode and become READY");
    if (!packed_reads || !destination_writes)
        throw std::runtime_error("read/write watch calibration failed during actual decode");
    const auto initial_reads = packed_reads, initial_writes = destination_writes;
    std::vector<uint8_t> decoded;
    unsigned mismatches = 0;
    for (const auto &part : {std::make_pair("wt_base.bin", "pk_pcm_wt_base"),
                             std::make_pair("wt_bank.bin", "pk_pcm_wt_bank")}) {
        const auto expected = read(assets + "/" + part.first);
        const auto address = symbols.at(part.second);
        for (unsigned i = 0; i < expected.size(); ++i) {
            const auto value = machine.read8(address + i);
            decoded.push_back(value);
            mismatches += value != expected[i];
        }
    }
    std::ofstream raw(output + "/callback-decoded-target.bin", std::ios::binary);
    raw.write(reinterpret_cast<const char *>(decoded.data()), decoded.size());
    if (decoded.size() != 200704 || mismatches)
        throw std::runtime_error("shipping guard decoded non-exact PCM bytes");
    // The READY guard must ignore the stream and preserve decoded storage.
    // This proves the shortcut dynamically, including a calibrated data watch.
    const uint32_t canary_a = symbols.at("pk_pcm_wt_base") + 17;
    const uint32_t canary_b = symbols.at("pk_pcm_wt_bank") + 123;
    const uint8_t value_a = machine.read8(canary_a) ^ 0x5a;
    const uint8_t value_b = machine.read8(canary_b) ^ 0xa5;
    machine.write8(canary_a, value_a);
    machine.write8(canary_b, value_b);
    machine.write8(symbols.at("pk_asset_pcm_rice"), 0);
    packed_reads = destination_writes = 0;
    const auto warm = call(machine, symbols.at("bench_callback_pcm"));
    if (m68k_get_reg(machine.getCpuState(), M68K_REG_D0) != 1 ||
        machine.read32(cookie) != ready || packed_reads || destination_writes ||
        machine.read8(canary_a) != value_a || machine.read8(canary_b) != value_b)
        throw std::runtime_error("READY guard reread/redecoded input or changed destinations");
    alignment.finish(output + "/callback-alignment.json");
    std::ofstream report(output + "/callback-result.json");
    report << "{\"shipping_source\":\"modules/perky/control_cf_final.c\","
           << "\"loaded_cold_cookie_outside_bss\":true,\"poisoned_bss_bytes\":" << bss_end - bss_start
           << ",\"decoded_bytes\":" << decoded.size() << ",\"byte_mismatches\":" << mismatches
           << ",\"rejected_cold_asset_counts\":[" << rejected_counts.str() << ']'
           << ",\"ready_after_decode\":true,\"first_decode_cycles\":" << initial.cycles
           << ",\"first_decode_instructions\":" << initial.instructions
           << ",\"first_decode_stack_bytes\":" << initial.stack
           << ",\"first_decode_packed_reads\":" << initial_reads
           << ",\"first_decode_destination_writes\":" << initial_writes
           << ",\"ready_call_cycles\":" << warm.cycles
           << ",\"ready_call_instructions\":" << warm.instructions
           << ",\"ready_call_stack_bytes\":" << warm.stack
           << ",\"ready_call_packed_reads\":" << packed_reads
           << ",\"ready_call_destination_writes\":" << destination_writes
           << ",\"ready_call_preserves_canaries\":true}\n";
    std::cout << "actual shipping PCM guard: poisoned BSS exact200704, READY shortcut "
              << warm.cycles << " cycles, zero packed reads and destination writes\n";
}
