// ColdFire cycle microbenchmark on the observer's own cycle model.
//
// Links the patched Musashi core (out/emu/mc68k/lib68kEmu.a: MCF5445x
// throughput table and branch predictor) that the frozen timing observer
// uses, plus an unmodified copy of ot_emu's v4e.cpp (MVS/MVZ, MOV3Q, ISA_C,
// the EMAC) behind the illegal-instruction callback, exactly as ot_emu runs
// it. Build with tools/harness/perky_cf/build_cf_cycle_bench.sh. It is a design
// aid for exact kernels, not an admission instrument: a candidate is only
// admitted by the full-image workload under the frozen observer.
//
// Usage: cf_cycle_bench CODE.bin SETUP.txt
//   CODE.bin is loaded at 0x10000 and entered there with a return address of
//   0xfff0 on the stack (an rts to it ends the run). SETUP.txt lines:
//     reg d0..d7/a0..a7 VALUE
//     mem ADDR FILE          (raw bytes from FILE at ADDR)
//     long ADDR VALUE        (big-endian 32-bit store)
//     word ADDR VALUE
//     push VALUE             (pushes a 32-bit argument, last pushed = first arg)
//     repeat N               (run the call N times, predictor kept warm)
//     dump ADDR BYTES        (hex dump after the last run)
//     elf FILE               (load .text/.rodata/.data PT_LOAD bytes at their
//                             addresses, masked to the 16 MB bench memory)
//     entry ADDR             (enter at ADDR instead of CODE.bin at 0x10000)
// Output: total cycles of the last run, instructions, predictor counters and
// cycles per PC offset (the observer attributes the same way).
#include "cpuState.h"
#include "mc68k.h"
#include "musashiEntry.h"
#include "machine.h"
#include "v4e.h"

#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <sstream>
#include <string>
#include <vector>

extern "C" {
extern uint64_t m68k_bcc_count, m68k_btb_hits, m68k_bht_hits, m68k_mispredicts;
}

namespace
{
	constexpr uint32_t kMemory = 0x01000000, kCode = 0x10000, kReturn = 0xfff0, kStack = 0x00ff0000;

	class Bench final : public ot::Machine
	{
	public:
		Bench() : Machine(M68K_CPU_TYPE_MCF5206E), memory(kMemory) {}
		using Mc68k::execInstruction;
		std::vector<uint8_t> memory;
		uint32_t unhandled = 0;
		uint8_t read8(uint32_t a) override { return memory[a & (kMemory - 1)]; }
		uint16_t read16(uint32_t a) override { return (read8(a) << 8) | read8(a + 1); }
		uint16_t readImm16(uint32_t a) override { return read16(a); }
		void write8(uint32_t a, uint8_t v) override { memory[a & (kMemory - 1)] = v; }
		void write16(uint32_t a, uint16_t v) override { write8(a, v >> 8); write8(a + 1, v); }
		uint32_t read32(uint32_t a) { return (uint32_t(read16(a)) << 16) | read16(a + 2); }
		void write32(uint32_t a, uint32_t v) { write16(a, v >> 16); write16(a + 2, v); }

		uint32_t reg(m68k_register_t r) { return m68k_get_reg(getCpuState(), r); }
		void setReg(m68k_register_t r, uint32_t v) { m68k_set_reg(getCpuState(), r, v); }
		m68k_register_t d(uint32_t i) { return static_cast<m68k_register_t>(M68K_REG_D0 + i); }
		m68k_register_t a(uint32_t i) { return static_cast<m68k_register_t>(M68K_REG_A0 + i); }
		uint16_t fetch16() { const auto p = reg(M68K_REG_PC); setReg(M68K_REG_PC, p + 2); return read16(p); }

		uint32_t onIllegalInstruction(uint32_t op) override
		{
			if(ot::v4e::execute(*this, op) == ot::v4e::Result::Handled) return 1;
			++unhandled;
			return 0;
		}
	};
}

int main(int argc, char** argv)
{
	if(argc != 3) { std::fprintf(stderr, "usage: %s CODE.bin SETUP.txt\n", argv[0]); return 2; }
	Bench cpu;
	std::ifstream code(argv[1], std::ios::binary);
	std::vector<uint8_t> blob{std::istreambuf_iterator<char>(code), {}};
	for(size_t k = 0; k < blob.size(); ++k) cpu.memory[(kCode + k) & (kMemory - 1)] = blob[k];
	std::ifstream setup(argv[2]);
	std::string line;
	std::map<std::string, uint32_t> regs;
	std::vector<uint32_t> pushes;
	std::vector<std::pair<uint32_t, uint32_t>> dumps;
	unsigned repeat = 1;
	uint32_t entry = kCode;
	while(std::getline(setup, line))
	{
		std::istringstream in(line);
		std::string kind; in >> kind;
		if(kind == "reg") { std::string r; std::string v; in >> r >> v; regs[r] = std::stoul(v, nullptr, 0); }
		else if(kind == "mem")
		{
			std::string at, file; in >> at >> file;
			std::ifstream f(file, std::ios::binary);
			std::vector<uint8_t> b{std::istreambuf_iterator<char>(f), {}};
			const uint32_t base = std::stoul(at, nullptr, 0);
			for(size_t k = 0; k < b.size(); ++k) cpu.memory[(base + k) & (kMemory - 1)] = b[k];
		}
		else if(kind == "long") { std::string at, v; in >> at >> v; cpu.write32(std::stoul(at, nullptr, 0), std::stoul(v, nullptr, 0)); }
		else if(kind == "word") { std::string at, v; in >> at >> v; cpu.write16(std::stoul(at, nullptr, 0), uint16_t(std::stoul(v, nullptr, 0))); }
		else if(kind == "push") { std::string v; in >> v; pushes.push_back(std::stoul(v, nullptr, 0)); }
		else if(kind == "repeat") in >> repeat;
		else if(kind == "entry") { std::string v; in >> v; entry = std::stoul(v, nullptr, 0); }
		else if(kind == "elf")
		{
			// 32-bit big-endian ELF program headers: copy each PT_LOAD's file bytes.
			std::string file; in >> file;
			std::ifstream f(file, std::ios::binary);
			std::vector<uint8_t> e{std::istreambuf_iterator<char>(f), {}};
			auto be32 = [&](size_t o) { return (uint32_t(e[o]) << 24) | (uint32_t(e[o + 1]) << 16) | (uint32_t(e[o + 2]) << 8) | e[o + 3]; };
			auto be16 = [&](size_t o) { return uint32_t((e[o] << 8) | e[o + 1]); };
			const uint32_t phoff = be32(28), phentsize = be16(42), phnum = be16(44);
			for(uint32_t i = 0; i < phnum; ++i)
			{
				const size_t h = phoff + size_t(i) * phentsize;
				if(be32(h) != 1) continue;
				const uint32_t off = be32(h + 4), vaddr = be32(h + 8), filesz = be32(h + 16);
				for(uint32_t k = 0; k < filesz; ++k) cpu.memory[(vaddr + k) & (kMemory - 1)] = e[off + k];
			}
		}
		else if(kind == "dump") { std::string at, n; in >> at >> n; dumps.push_back({std::stoul(at, nullptr, 0), std::stoul(n, nullptr, 0)}); }
	}
	const auto snapshot = cpu.memory;
	std::map<uint32_t, uint64_t> perPc;
	uint64_t total = 0, instructions = 0, bcc = 0, miss = 0;
	for(unsigned run = 0; run < repeat; ++run)
	{
		// Every run starts from the same memory and registers; only the
		// predictor state carries over, as it does between frames.
		if(run) cpu.memory = snapshot;
		uint32_t sp = kStack;
		for(auto it = pushes.rbegin(); it != pushes.rend(); ++it) { sp -= 4; cpu.write32(sp, *it); }
		sp -= 4; cpu.write32(sp, kReturn);
		for(unsigned i = 0; i < 8; ++i) cpu.setReg(cpu.d(i), 0);
		for(unsigned i = 0; i < 7; ++i) cpu.setReg(cpu.a(i), 0);
		for(const auto& [r, v] : regs)
			cpu.setReg(r[0] == 'd' ? cpu.d(r[1] - '0') : cpu.a(r[1] - '0'), v);
		cpu.setReg(M68K_REG_SP, sp);
		cpu.setReg(M68K_REG_SR, 0x2700);
		cpu.setPC(entry);
		const auto bccBefore = m68k_bcc_count, missBefore = m68k_mispredicts;
		uint64_t cycles = 0, count = 0;
		perPc.clear();
		while(cpu.getPC() != kReturn)
		{
			const uint32_t pc = cpu.getPC();
			if(std::getenv("BENCH_TRACE") && count < 40) std::fprintf(stderr, "pc %08x op %04x a7 %08x\n", pc, cpu.read16(pc), cpu.reg(M68K_REG_SP));
			uint32_t c;
			// As ot_emu's Machine::step: A-line (EMAC, MOV3Q) goes straight to
			// the V4e layer without a Musashi instruction, so it costs 0 cycles.
			const uint16_t op = cpu.read16(pc);
			if((op & 0xf000) == 0xa000)
			{
				cpu.setPC(pc + 2);
				if(ot::v4e::execute(cpu, op) != ot::v4e::Result::Handled) { std::fprintf(stderr, "unhandled A-line %04x at %08x\n", op, pc); return 5; }
				c = 0;
			}
			else
				c = cpu.execInstruction();
			perPc[pc - entry] += c; cycles += c; ++count;
			if(count > 50'000'000) { std::fprintf(stderr, "runaway at 0x%x\n", pc); return 3; }
		}
		total = cycles; instructions = count; bcc = m68k_bcc_count - bccBefore; miss = m68k_mispredicts - missBefore;
	}
	std::printf("{\"cycles\":%llu,\"instructions\":%llu,\"bcc\":%llu,\"mispredicts\":%llu,\"unhandled\":%u,\"d0\":%u,\"pc\":{",
		(unsigned long long)total, (unsigned long long)instructions, (unsigned long long)bcc,
		(unsigned long long)miss, cpu.unhandled, cpu.reg(cpu.d(0)));
	bool comma = false;
	for(const auto& [pc, c] : perPc) { std::printf("%s\"%x\":%llu", comma ? "," : "", pc, (unsigned long long)c); comma = true; }
	std::printf("},\"dumps\":[");
	comma = false;
	for(const auto& [at, n] : dumps)
	{
		std::printf("%s\"", comma ? "," : "");
		for(uint32_t i = 0; i < n; ++i) std::printf("%02x", cpu.read8(at + i));
		std::printf("\""); comma = true;
	}
	std::printf("]}\n");
	return cpu.unhandled ? 4 : 0;
}
